import os

from django.core.files.base import ContentFile

from funkwhale_api.common import preferences
from funkwhale_api.federation import activity
from funkwhale_api.federation import actors
from funkwhale_api.federation import models as federation_models
from funkwhale_api.federation import serializers as federation_serializers
from funkwhale_api.taskapp import celery
from funkwhale_api.providers.acoustid import get_acoustid_client
from funkwhale_api.providers.audiofile import tasks as audiofile_tasks

from django.conf import settings
from . import models
from . import lyrics as lyrics_utils
from . import utils as music_utils


@celery.app.task(name='acoustid.set_on_track_file')
@celery.require_instance(models.TrackFile, 'track_file')
def set_acoustid_on_track_file(track_file):
    client = get_acoustid_client()
    result = client.get_best_match(track_file.audio_file.path)

    def update(id):
        track_file.acoustid_track_id = id
        track_file.save(update_fields=['acoustid_track_id'])
        return id
    if result:
        return update(result['id'])


def import_track_from_remote(library_track):
    metadata = library_track.metadata
    try:
        track_mbid = metadata['recording']['musicbrainz_id']
        assert track_mbid  # for null/empty values
    except (KeyError, AssertionError):
        pass
    else:
        return models.Track.get_or_create_from_api(mbid=track_mbid)[0]

    try:
        album_mbid = metadata['release']['musicbrainz_id']
        assert album_mbid  # for null/empty values
    except (KeyError, AssertionError):
        pass
    else:
        album, _ = models.Album.get_or_create_from_api(mbid=album_mbid)
        return models.Track.get_or_create_from_title(
            library_track.title, artist=album.artist, album=album)[0]

    try:
        artist_mbid = metadata['artist']['musicbrainz_id']
        assert artist_mbid  # for null/empty values
    except (KeyError, AssertionError):
        pass
    else:
        artist, _ = models.Artist.get_or_create_from_api(mbid=artist_mbid)
        album, _ = models.Album.get_or_create_from_title(
            library_track.album_title, artist=artist)
        return models.Track.get_or_create_from_title(
            library_track.title, artist=artist, album=album)[0]

    # worst case scenario, we have absolutely no way to link to a
    # musicbrainz resource, we rely on the name/titles
    artist, _ = models.Artist.get_or_create_from_name(
        library_track.artist_name)
    album, _ = models.Album.get_or_create_from_title(
        library_track.album_title, artist=artist)
    return models.Track.get_or_create_from_title(
        library_track.title, artist=artist, album=album)[0]


def _do_import(import_job, replace=False, use_acoustid=False):
    from_file = bool(import_job.audio_file)
    mbid = import_job.mbid
    acoustid_track_id = None
    duration = None
    track = None
    # use_acoustid = use_acoustid and preferences.get('providers_acoustid__api_key')
    # Acoustid is not reliable, we disable it for now.
    use_acoustid = False
    if not mbid and use_acoustid and from_file:
        # we try to deduce mbid from acoustid
        client = get_acoustid_client()
        match = client.get_best_match(import_job.audio_file.path)
        if match:
            duration = match['recordings'][0]['duration']
            mbid = match['recordings'][0]['id']
            acoustid_track_id = match['id']
    if mbid:
        track, _ = models.Track.get_or_create_from_api(mbid=mbid)
    elif import_job.audio_file:
        track = audiofile_tasks.import_track_data_from_path(
            import_job.audio_file.path)
    elif import_job.library_track:
        track = import_track_from_remote(import_job.library_track)
    elif import_job.source.startswith('file://'):
        track = audiofile_tasks.import_track_data_from_path(
            import_job.source.replace('file://', '', 1))
    else:
        raise ValueError(
            'Not enough data to process import, '
            'add a mbid, an audio file or a library track')

    track_file = None
    if replace:
        track_file = track.files.first()
    elif track.files.count() > 0:
        if import_job.audio_file:
            import_job.audio_file.delete()
        import_job.status = 'skipped'
        import_job.save()
        return

    track_file = track_file or models.TrackFile(
        track=track, source=import_job.source)
    track_file.acoustid_track_id = acoustid_track_id
    if from_file:
        track_file.audio_file = ContentFile(import_job.audio_file.read())
        track_file.audio_file.name = import_job.audio_file.name
        track_file.duration = duration
    elif import_job.library_track:
        track_file.library_track = import_job.library_track
        track_file.mimetype = import_job.library_track.audio_mimetype
        if import_job.library_track.library.download_files:
            raise NotImplementedError()
        else:
            # no downloading, we hotlink
            pass
    elif not import_job.audio_file and not import_job.source.startswith('file://'):
        # not an implace import, and we have a source, so let's download it
        track_file.download_file()
    elif not import_job.audio_file and import_job.source.startswith('file://'):
        # in place import, we set mimetype from extension
        path, ext = os.path.splitext(import_job.source)
        track_file.mimetype = music_utils.get_type_from_ext(ext)
    track_file.set_audio_data()
    track_file.save()
    import_job.status = 'finished'
    import_job.track_file = track_file
    if import_job.audio_file:
        # it's imported on the track, we don't need it anymore
        import_job.audio_file.delete()
    import_job.save()

    return track_file


@celery.app.task(name='ImportJob.run', bind=True)
@celery.require_instance(
    models.ImportJob.objects.filter(
        status__in=['pending', 'errored']),
    'import_job')
def import_job_run(self, import_job, replace=False, use_acoustid=False):
    def mark_errored():
        import_job.status = 'errored'
        import_job.save(update_fields=['status'])

    try:
        tf = _do_import(import_job, replace, use_acoustid=use_acoustid)
        return tf.pk if tf else None
    except Exception as exc:
        if not settings.DEBUG:
            try:
                self.retry(exc=exc, countdown=30, max_retries=3)
            except:
                mark_errored()
                raise
        mark_errored()
        raise


@celery.app.task(name='ImportBatch.run')
@celery.require_instance(models.ImportBatch, 'import_batch')
def import_batch_run(import_batch):
    for job_id in import_batch.jobs.order_by('id').values_list('id', flat=True):
        import_job_run.delay(import_job_id=job_id)


@celery.app.task(name='Lyrics.fetch_content')
@celery.require_instance(models.Lyrics, 'lyrics')
def fetch_content(lyrics):
    html = lyrics_utils._get_html(lyrics.url)
    content = lyrics_utils.extract_content(html)
    cleaned_content = lyrics_utils.clean_content(content)
    lyrics.content = cleaned_content
    lyrics.save(update_fields=['content'])


@celery.app.task(name='music.import_batch_notify_followers')
@celery.require_instance(
    models.ImportBatch.objects.filter(status='finished'), 'import_batch')
def import_batch_notify_followers(import_batch):
    if not preferences.get('federation__enabled'):
        return

    if import_batch.source == 'federation':
        return

    library_actor = actors.SYSTEM_ACTORS['library'].get_actor_instance()
    followers = library_actor.get_approved_followers()
    jobs = import_batch.jobs.filter(
        status='finished',
        library_track__isnull=True,
        track_file__isnull=False,
    ).select_related(
        'track_file__track__artist',
        'track_file__track__album__artist',
    )
    track_files = [job.track_file for job in jobs]
    collection = federation_serializers.CollectionSerializer({
        'actor': library_actor,
        'id': import_batch.get_federation_url(),
        'items': track_files,
        'item_serializer': federation_serializers.AudioSerializer
    }).data
    for f in followers:
        create = federation_serializers.ActivitySerializer(
            {
                'type': 'Create',
                'id': collection['id'],
                'object': collection,
                'actor': library_actor.url,
                'to': [f.url],
            }
        ).data

        activity.deliver(create, on_behalf_of=library_actor, to=[f.url])

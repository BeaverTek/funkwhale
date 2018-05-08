from funkwhale_api.subsonic import serializers


def test_get_artists_serializer(factories):
    artist1 = factories['music.Artist'](name='eliot')
    artist2 = factories['music.Artist'](name='Ellena')
    artist3 = factories['music.Artist'](name='Rilay')

    factories['music.Album'].create_batch(size=3, artist=artist1)
    factories['music.Album'].create_batch(size=2, artist=artist2)

    expected = {
        'ignoredArticles': '',
        'index': [
            {
                'name': 'E',
                'artist': [
                    {
                        'id': artist1.pk,
                        'name': artist1.name,
                        'albumCount': 3,
                    },
                    {
                        'id': artist2.pk,
                        'name': artist2.name,
                        'albumCount': 2,
                    },
                ]
            },
            {
                'name': 'R',
                'artist': [
                    {
                        'id': artist3.pk,
                        'name': artist3.name,
                        'albumCount': 0,
                    },
                ]
            },
        ]
    }

    queryset = artist1.__class__.objects.filter(pk__in=[
        artist1.pk, artist2.pk, artist3.pk
    ])

    assert serializers.GetArtistsSerializer(queryset).data == expected


def test_get_artist_serializer(factories):
    artist = factories['music.Artist']()
    album = factories['music.Album'](artist=artist)
    tracks = factories['music.Track'].create_batch(size=3, album=album)

    expected = {
        'id': artist.pk,
        'name': artist.name,
        'albumCount': 1,
        'album': [
            {
                'id': album.pk,
                'artistId': artist.pk,
                'name': album.title,
                'artist': artist.name,
                'songCount': len(tracks),
                'created': album.creation_date,
                'year': album.release_date.year,
            }
        ]
    }

    assert serializers.GetArtistSerializer(artist).data == expected


def test_get_album_serializer(factories):
    artist = factories['music.Artist']()
    album = factories['music.Album'](artist=artist)
    track = factories['music.Track'](album=album)
    tf = factories['music.TrackFile'](track=track)

    expected = {
        'id': album.pk,
        'artistId': artist.pk,
        'name': album.title,
        'artist': artist.name,
        'songCount': 1,
        'created': album.creation_date,
        'year': album.release_date.year,
        'song': [
            {
                'id': track.pk,
                'isDir': False,
                'title': track.title,
                'album': album.title,
                'artist': artist.name,
                'track': track.position,
                'year': track.album.release_date.year,
                'contentType': tf.mimetype,
                'suffix': tf.extension,
                'duration': tf.duration,
                'created': track.creation_date,
                'albumId': album.pk,
                'artistId': artist.pk,
                'type': 'music',
            }
        ]
    }

    assert serializers.GetAlbumSerializer(album).data == expected

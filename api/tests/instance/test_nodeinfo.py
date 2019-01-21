import funkwhale_api
from funkwhale_api.instance import nodeinfo


def test_nodeinfo_dump(preferences, mocker):
    preferences["instance__nodeinfo_stats_enabled"] = True
    stats = {
        "users": {"total": 1, "active_halfyear": 12, "active_month": 13},
        "tracks": 2,
        "albums": 3,
        "artists": 4,
        "track_favorites": 5,
        "music_duration": 6,
        "listenings": 7,
    }
    mocker.patch("funkwhale_api.instance.stats.get", return_value=stats)

    expected = {
        "version": "2.0",
        "software": {"name": "funkwhale", "version": funkwhale_api.__version__},
        "protocols": ["activitypub"],
        "services": {"inbound": [], "outbound": []},
        "openRegistrations": preferences["users__registration_enabled"],
        "usage": {"users": {"total": 1, "activeHalfyear": 12, "activeMonth": 13}},
        "metadata": {
            "private": preferences["instance__nodeinfo_private"],
            "shortDescription": preferences["instance__short_description"],
            "longDescription": preferences["instance__long_description"],
            "nodeName": preferences["instance__name"],
            "library": {
                "federationEnabled": preferences["federation__enabled"],
                "federationNeedsApproval": preferences[
                    "federation__music_needs_approval"
                ],
                "anonymousCanListen": not preferences[
                    "common__api_authentication_required"
                ],
                "tracks": {"total": stats["tracks"]},
                "artists": {"total": stats["artists"]},
                "albums": {"total": stats["albums"]},
                "music": {"hours": stats["music_duration"]},
            },
            "usage": {
                "favorites": {"tracks": {"total": stats["track_favorites"]}},
                "listenings": {"total": stats["listenings"]},
            },
        },
    }
    assert nodeinfo.get() == expected


def test_nodeinfo_dump_stats_disabled(preferences, mocker):
    preferences["instance__nodeinfo_stats_enabled"] = False

    expected = {
        "version": "2.0",
        "software": {"name": "funkwhale", "version": funkwhale_api.__version__},
        "protocols": ["activitypub"],
        "services": {"inbound": [], "outbound": []},
        "openRegistrations": preferences["users__registration_enabled"],
        "usage": {"users": {"total": 0, "activeHalfyear": 0, "activeMonth": 0}},
        "metadata": {
            "private": preferences["instance__nodeinfo_private"],
            "shortDescription": preferences["instance__short_description"],
            "longDescription": preferences["instance__long_description"],
            "nodeName": preferences["instance__name"],
            "library": {
                "federationEnabled": preferences["federation__enabled"],
                "federationNeedsApproval": preferences[
                    "federation__music_needs_approval"
                ],
                "anonymousCanListen": not preferences[
                    "common__api_authentication_required"
                ],
            },
        },
    }
    assert nodeinfo.get() == expected

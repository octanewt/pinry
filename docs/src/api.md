# API Support

Pinry support API accessing via token so that you could write your own client or import any pin format to your instance.

# Get Token
Just go to `My -> Profile` page to get the token.

![token-accessing](./imgs/screenshots/token-access.png)

# Access API via Token

Here is an example for curl to access `user-profile` API:

    curl -X GET http://192.168.1.101:8080/api/v2/profile/users/ -H 'Authorization: Token fa3b0ed2b8a87c81323688c288642288c9570aca'

You will get response like this:

    [
        {
        "username": "winkidney",
        "token": "fa3b0ed2b8a87c81323688c288642288c9570aca",
        "email": "winkidney@gmail.com",
        "gravatar": "0d7161ac663cdb21108502cd4051149c",
        "resource_link": "http://localhost:8000/api/v2/profile/users/1/"
        }
    ]

`email` and `token` are only returned to the user themself, through `/api/v2/profile/users/`.

# Other ways to authenticate

The SPA uses a session: `POST /api/v2/profile/login/` with a JSON body of `username` (or email) and `password`, and `POST /api/v2/profile/logout/` to log out. Both need the `X-CSRFToken` header. Logging out with `GET` is not supported.

HTTP Basic auth (`curl -u user:password`) is off by default. Set `ALLOW_BASIC_AUTH = True` in `local_settings.py` to turn it on; a token is the better choice for scripts.

Failed password checks are limited per client address (20 an hour by default, from the SPA, the admin login and Basic auth together); past that the login answers `429` with a `Retry-After` header. Change it with `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["login"]` in `local_settings.py`, or set it to `None` to turn it off.

With `PUBLIC = False`, token (and enabled Basic) requests still work; anonymous requests get `403`.

# Other users

Pins and boards embed their owner as `submitter`, and `/api/v2/profile/public-users/?username=<name>` describes any user. Both return only public fields:

    {
        "username": "winkidney",
        "gravatar": "0d7161ac663cdb21108502cd4051149c",
        "resource_link": "http://localhost:8000/api/v2/profile/public-users/1/"
    }

Before this change, `submitter` and `public-users` also returned `email` (to anyone) and `token` (to the user themself). Clients that read either field from there should use `/api/v2/profile/users/` instead.

# Privacy filters

Private pins and boards are only visible to their owner, and the API applies this everywhere:

- `/api/v2/pins/?pins__id=<board id>` lists a board's pins, and returns nothing for a private board of another user.
- A board's `cover` is chosen among the pins the requester can see.
- `/api/v2/tags-auto-complete/` lists only tags used on pins the requester can see.


# API reference
Just use the interactive API interface by DRF or follow the file [api.js](https://github.com/pinry/pinry/blob/master/pinry-spa/src/components/api.js)

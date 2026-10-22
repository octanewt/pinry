Upgrade Guide
---------------------

This doc is about how you should do to upgrade specified version to next version.

Generally, you should have no extra action to take if you use our docker version
if we haven't written notes for it.

If you meet some errors which include `no such table`, please have a try to run migrations in docker:
```
# out of docker
docker exec -it <your-container-id> bash
# in docker
python manage.py migrate 
```

How to get the current version with source code:
```
git tag
```
The first line of output is our latest version of code.


# Deployment hardening (unreleased)
+ The Docker image now runs `migrate` on every start, so new migrations are
  applied after an upgrade.
+ Pinry refuses to start if `SECRET_KEY` is unset or still a placeholder.
  The Docker image's generated `/data/local_settings.py` already has one.
+ `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `HTTPS` and `HSTS_SECONDS` can be
  set as environment variables, see [Install with Docker](install-with-docker.md).
  Setting `ALLOWED_HOSTS` is recommended.
+ New installs no longer enable the example plugin. Existing
  `/data/local_settings.py` files are not changed; remove
  `pinry_plugins.batteries.plugin_example.Plugin` from `ENABLED_PLUGINS` there
  if you don't use it.

# v2.1.6 -> v2.1.7
v2.1.6 has a security issue which may cause unauthorized token-read.
If you upgrade your instance from v2.1.6 to v2.1.7, you could go into 
docker and run following command to reset tokens.
```
python manage.py users_reset_tokens
```

# v2.0.2 -> v2.1.0
Main breaking changes:

+  Upgrade `django 1` to django `2.2 LTS`

How to:

If you use non-docker version, you should change your web-server config to add a new
alias for `media file path` (where to store images).

Please add following config to your nginx config in `server` block:
```
location /media {
    alias /path/to/static/media;
    expires max;
    access_log off;
}
```

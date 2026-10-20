# CLAUDE.md

This file guides Claude Code (claude.ai/code) when working in this repository.

## Fork and upstream

This repository is `octanewt/pinry`, a fork of `pinry/pinry` (upstream). Open pull requests against this fork's `master`. Don't open a pull request on `pinry/pinry`, or offer to, unless the user explicitly asks for one.

## Project overview

Pinry is a self-hosted, Pinterest-style image board. It has two parts:

- **Backend**: Django 2.2 (`django>2.2.17,<3`) with Django REST Framework. It serves a JSON API under `/api/v2/` and the Django admin. Dependencies are managed with **Poetry** (`pyproject.toml`, `poetry.lock`). The `requirements.txt` and `requirements-dev.txt` files are generated from Poetry and used by CI and the Docker build.
- **Frontend**: a Vue 2 single-page app in `pinry-spa/` (Buefy, vue-router, vue-masonry, vue-i18n, axios). It is built with Vue CLI 4 and managed with **pnpm** (`pnpm-lock.yaml`).

The backend does not render the app's pages; the SPA does all UI. In production (Docker), nginx serves `pinry-spa/dist` for `/`, serves `/static` and `/media` from `/data/static`, and proxies `/api` and `/admin` to gunicorn.

## Common commands

Backend (from the repo root, see `Makefile`):

```sh
poetry install                              # make install
poetry run python manage.py migrate         # make migrate
poetry run python manage.py runserver       # make serve (binds 0.0.0.0:8000)
poetry run python manage.py test            # make test, runs all Django tests
poetry run python manage.py test core.tests.api.PinTests   # one test class
poetry run flake8                           # make flake8
poetry run python manage.py makemigrations  # make makemigrations
make export-requirements                    # regenerate requirements*.txt after changing pyproject.toml
poetry run mkdocs serve                     # make docs-serve (docs in docs/src)
```

Frontend (from `pinry-spa/`, Node 18):

```sh
pnpm install
pnpm serve    # dev server; proxies /api, /media, /static/js/ to 127.0.0.1:8000
pnpm build    # production build into pinry-spa/dist (CI runs this)
pnpm lint     # ESLint, airbnb + plugin:vue config
```

The npm scripts set `NODE_OPTIONS=--openssl-legacy-provider`, which Vue CLI 4 needs on Node 18.

For local development, run `manage.py runserver` and `pnpm serve` at the same time.

CI (`.github/workflows/`) does the following:

- **Backend:** runs `pip install -r requirements-dev.txt`, then `make flake8-in-ci` and `make test-in-ci` on Python 3.7, 3.8 and 3.9.
- **Frontend:** runs `pnpm install && pnpm build` on Node 18.

Keep code compatible with Python 3.7: no walrus operator, no positional-only parameters, and no `dict | dict`. When you change dependencies in `pyproject.toml`, also update `poetry.lock` and the exported `requirements*.txt` files. CI and Docker install only from the requirements files.

## Settings

- `manage.py` defaults to `pinry.settings.development` unless `DJANGO_SETTINGS_MODULE` or `--settings` is given. The development settings use SQLite at `db.sqlite3`, set `DEBUG=True` and add `django_extensions`. `manage.py` also sets `settings.IS_TEST = True` whenever `test` is in argv, and when `IS_TEST` is true, `pinry/urls.py` also serves static files.
- `pinry/settings/base.py` holds the shared config, including `PUBLIC`, `ALLOW_NEW_REGISTRATIONS`, `IMAGE_SIZES`, `IMAGE_PATH`, `IMAGE_AUTO_DELETE` and the DRF config:
  - Authentication: Basic, Token and Session.
  - Pagination: LimitOffset, with `PAGE_SIZE=50`.
  - `URL_FIELD_NAME="resource_link"`.
- `pinry/settings/docker.py` is the production config. It is selected with `ENV DJANGO_SETTINGS_MODULE` in `Dockerfile.autobuild` and `_start_gunicorn.sh`, not with a `--settings` flag. It uses Postgres at host `db`, reads `SECRET_KEY` from the environment, and **requires** a `local_settings.py`. See `local_settings.example.py`.
- `local_settings.py` is optional in development and gitignored. It overrides settings and is where `ENABLED_PLUGINS` is set.

## Architecture

Django apps:

- **`core/`** holds the domain models `Pin`, `Board` and `Image` (`core.Image` subclasses `django_images.Image`). It also holds:
  - The DRF viewsets and router (`core/views.py`, `drf_router`), mounted at `/api/v2/`: `pins`, `images`, `boards`, `tags-auto-complete` and `boards-auto-complete`.
  - The serializers and the permissions (`IsOwnerOrReadOnly`, `OwnerOnlyIfPrivate`, ...).

  Details:
  - **Privacy**: private boards and pins are filtered for non-owners in `core/serializers.py` (`filter_private_pin`, `filter_private_board`) and in the viewset querysets. Any change to how pins or boards are listed must keep this filtering.
  - `Pin.url` and `Pin.referer` hold up to 2048 characters. `referer` is labelled "Source" in the UI.
  - When an image is fetched from a URL, it is checked with Pillow (`ImageManager._is_valid_image`) and rejected if Pillow can't open it.
  - Tags use `django-taggit` (pinned at 1.3.0). Filtering uses `django-filter` (pinned at 2.4.0).
  - Multi-tag search is in `core/filters.py` (`TagsFilterBackend`): `/api/v2/pins/?tags=a&tags=b&tags_mode=all|any`, defaulting to `all`. The frontend sends repeated `tags=` keys through `serializeParams` in `api.js`.
- **`django_images/`** is a vendored image library. It provides the base `Image` and `Thumbnail` models, MD5-hashed upload paths, and thumbnail generation at the sizes in `IMAGE_SIZES`. Signal handlers delete files on disk when rows are deleted (`IMAGE_AUTO_DELETE`).
- **`users/`** has the custom `User` model, the login and logout views, and the `users` and `public-users` viewsets, mounted at `/api/v2/profile/`.
  - `users.auth.backends.CombinedAuthBackend` lets users log in with username or email.
  - `users.middleware.Public` returns 403 to anonymous requests when `PUBLIC=False`, except for `/api/v2/profile/`.
  - **API tokens** (`rest_framework.authtoken`): a `post_save` signal creates a token for every user (`create_token_if_necessary`). `UserSerializer.get_token` returns it only when the requester is that user. `manage.py users_reset_tokens` deletes all tokens. Unauthenticated API requests get 401, not 403. See `docs/src/api.md`.
- **`pinry_plugins/`** is the plugin system.
  - Each class path in `settings.ENABLED_PLUGINS` is instantiated in `builder/_loader.py`.
  - `pre_save` signal handlers call the hooks `process_image_pre_creation` and `process_thumbnail_pre_creation` on new `core.Image` and `Thumbnail` rows, catching and logging any exception a plugin raises.
  - `batteries/plugin_example.py` shows the interface. See `docs/src/plugin-system.md`.
- **`pinry/`** is the project package: settings, root `urls.py`, and `middleware.py` (`ForceCSRFCookieMiddleware`, which makes sure the SPA gets a CSRF cookie). It also contains the bookmarklet, `pinry/static/js/bookmarklet.js`.

Frontend (`pinry-spa/src/`):

- `components/api.js` is the single API client. It wraps axios calls to `/api/v2/` in objects such as `Board`, `Pin`, `User` and `Tag`. Add new backend calls here instead of calling axios from components.
- `router/index.js` defines the routes, which map to `views/` (`Pins4Board`, `Pins4Tag`, `Pins4User`, `Profile4User`, `Search`, ...). Reusable UI lives in `components/`:
  - Editors and modals are under `components/editors/` and `components/pin_edit/`.
  - The profile and API-token UI is in `components/user/`.
- **i18n**: user-facing strings go through vue-i18n (`$t(...)`). The locale files are `components/utils/i18n/locales/{en,zh,fr}.json`, registered in `components/utils/i18n/index.js`. When you add a string, add its key to `en.json` at minimum, and to the other locales when you can. The chosen language is saved in local storage.

## Tests

- Backend tests live in `core/tests/` (`api.py` and `views.py`, re-exported from `core/tests/__init__.py`, so register new test modules there), `users/tests.py`, `django_images/tests.py` and `pinry_plugins/tests.py`.
- Use the fixture helpers in `core/tests/helpers.py` (`create_user`, `create_image`, `create_pin`, `create_tag`). Their test image is `docs/src/imgs/logo-dark.png`, so that file must stay where it is.
- API tests use DRF's `APITestCase`.
- The frontend has no test suite. `pnpm lint` and `pnpm build` are the checks.

## Conventions

- flake8 config is in `.flake8`: max line length 80, but E501 is ignored. Migrations, `pinry/settings/` and `core/tests/` are excluded. Bugbear (`B`) checks are selected.
- `black==19.10b0` is a dev dependency but is not enforced in CI. Match the style of the surrounding code.
- After changing models, generate migrations with `manage.py makemigrations` and commit them. Don't hand-edit existing migrations.
- Frontend code follows the airbnb ESLint rules (2-space indent, semicolons, trailing commas).

## Docker

- `Dockerfile.autobuild` builds the release image (`getpinry/pinry`). It is a single image with nginx, gunicorn and the built SPA, installs from `requirements.txt` and supports multiple platforms, including ARM.
- `Dockerfile` and `docker-compose.example.yml` are for development.
- Build scripts are in `docker/` (`build_docker.sh`, `build_docker_multiple_platform.sh`). Runtime scripts are in `docker/scripts/` (`start.sh`, `bootstrap.sh`, `gen_key.sh`), and the nginx config, which sends `X-Frame-Options: sameorigin`, is in `docker/nginx/`.
- Persistent data (the database, static files and media) lives in the `/data` volume.

# CLAUDE.md

This file guides Claude Code (claude.ai/code) when working in this repository.

## Project overview

Pinry is a self-hosted, Pinterest-style image board. It has two parts:

- **Backend**: Django 2.2 (`django>2.2,<3`) with Django REST Framework. It serves a JSON API under `/api/v2/` and the Django admin. Dependencies are managed with **pipenv** (`Pipfile`).
- **Frontend**: a Vue 2 single-page app in `pinry-spa/` (Buefy, vue-router, vue-masonry, axios). It is built with Vue CLI 4 and managed with **yarn**.

The backend does not render the app's pages; the SPA does all UI. In production (Docker), nginx serves `pinry-spa/dist` for `/`, serves `/static` and `/media` from `/data/static`, and proxies `/api` and `/admin` to gunicorn.

## Common commands

Backend (from the repo root, see `Makefile`):

```sh
pipenv install --dev                       # install (CI uses: pipenv install --dev --system)
pipenv run python manage.py migrate        # make migrate
pipenv run python manage.py runserver      # make serve (binds 0.0.0.0:8000)
pipenv run python manage.py test           # make test, runs all Django tests
pipenv run python manage.py test core.tests.api.PinTests   # one test class
pipenv run flake8                          # make flake8 (lint, as CI runs it)
pipenv run python manage.py makemigrations # make makemigrations
pipenv run mkdocs serve                    # make docs-serve (docs in docs/src)
```

Frontend (from `pinry-spa/`):

```sh
yarn install
yarn serve    # dev server; proxies /api, /media, /static/js/ to localhost:8000
yarn build    # production build into pinry-spa/dist (CI runs this)
yarn lint     # ESLint, airbnb + plugin:vue config (.eslintrc.js)
```

For local development, run `manage.py runserver` and `yarn serve` at the same time.

CI (`.github/workflows/`) runs `make flake8` and `python manage.py test` on Python 3.6 to 3.9, plus `yarn install && yarn build` on Node 8 to 14. Keep code compatible with Python 3.6, so no walrus operator and no `dict | dict`.

## Settings

- `manage.py` defaults to `pinry.settings.development` (SQLite at `db.sqlite3`, `DEBUG=True`, adds `django_extensions`). It sets `settings.IS_TEST = True` whenever `test` is in argv. When `IS_TEST` is true, `pinry/urls.py` also serves static files.
- `pinry/settings/base.py` holds the shared config, including `PUBLIC`, `ALLOW_NEW_REGISTRATIONS`, `IMAGE_SIZES`, `IMAGE_PATH`, `IMAGE_AUTO_DELETE` and the DRF config (LimitOffset pagination, `PAGE_SIZE=50`, `URL_FIELD_NAME="resource_link"`).
- `pinry/settings/docker.py` is the production config used in Docker: Postgres at host `db`, `SECRET_KEY` read from the environment, and it **requires** a `local_settings.py`. See `local_settings.example.py`.
- `local_settings.py` is optional in development and gitignored. It overrides settings and is where `ENABLED_PLUGINS` is set.

## Architecture

Django apps:

- **`core/`** holds the domain models `Pin`, `Board` and `Image` (`core.Image` subclasses `django_images.Image`). It also holds the DRF viewsets and router (`core/views.py`, `drf_router`, mounted at `/api/v2/`: `pins`, `images`, `boards`, `tags-auto-complete`, `boards-auto-complete`), the serializers, and the permissions (`IsOwnerOrReadOnly`, `OwnerOnlyIfPrivate`, ...).
  - **Privacy**: private boards and pins are filtered for non-owners in `core/serializers.py` (`filter_private_pin`, `filter_private_board`) and in the viewset querysets. Any change to how pins or boards are listed must keep this filtering.
  - Tags use `django-taggit`. Filtering uses `django-filter` (pinned at 2.2.0).
- **`django_images/`** is a vendored image library. It provides the base `Image` and `Thumbnail` models, MD5-hashed upload paths, and thumbnail generation at the sizes in `IMAGE_SIZES`. Signal handlers delete files on disk when rows are deleted (`IMAGE_AUTO_DELETE`).
- **`users/`** has the custom `User` model, login and logout views, and the `users` and `public-users` viewsets, mounted at `/api/v2/profile/`. `users.auth.backends.CombinedAuthBackend` lets users log in with username or email. `users.middleware.Public` returns 403 to anonymous requests when `PUBLIC=False`, except for `/api/v2/profile/`.
- **`pinry_plugins/`** is the plugin system. Each class path in `settings.ENABLED_PLUGINS` is instantiated in `builder/_loader.py`. `pre_save` signal handlers call the hooks `process_image_pre_creation` and `process_thumbnail_pre_creation` on new `core.Image` and `Thumbnail` rows, catching and logging any exception a plugin raises. `batteries/plugin_example.py` shows the interface. See `docs/src/plugin-system.md`.
- **`pinry/`** is the project package: settings, root `urls.py`, and `middleware.py` (`ForceCSRFCookieMiddleware`, which makes sure the SPA gets a CSRF cookie).

Frontend (`pinry-spa/src/`):

- `components/api.js` is the single API client. It wraps axios calls to `/api/v2/` in objects such as `Board`, `Pin` and `User`. Add new backend calls here instead of calling axios from components.
- `router/index.js` defines the routes, which map to `views/` (`Pins4Board`, `Pins4Tag`, `Pins4User`, `Search`, ...). Reusable UI lives in `components/`, with editors and modals under `components/editors/` and `components/pin_edit/`.

## Tests

- Backend tests live in `core/tests/` (`api.py` and `views.py`, re-exported from `core/tests/__init__.py`, so register new test modules there), `users/tests.py`, `django_images/tests.py` and `pinry_plugins/tests.py`.
- Use the fixtures helpers in `core/tests/helpers.py` (`create_user`, `create_image`, `create_pin`, `create_tag`). Their test image is `docs/src/imgs/logo-dark.png`, so that file must stay where it is.
- API tests use DRF's `APITestCase`.
- The frontend has no test suite. `yarn lint` and `yarn build` are the checks.

## Conventions

- flake8 config is in `.flake8`: max line length 80, but E501 is ignored. Migrations, `pinry/settings/` and `core/tests/` are excluded. Bugbear (`B`) checks are selected.
- `black==19.10b0` is a dev dependency but is not enforced in CI. Match the style of the surrounding code.
- After changing models, generate migrations with `manage.py makemigrations` and commit them. Don't hand-edit existing migrations.
- Frontend code follows the airbnb ESLint rules (2-space indent, semicolons, trailing commas).

## Docker

- `Dockerfile` and `Dockerfile.autobuild` build a single image with nginx, gunicorn and the built SPA. `docker-compose.example.yml` shows a compose setup.
- Scripts are in `docker/scripts/` (`start.sh`, `bootstrap.sh`, `gen_key.sh`), and the nginx config is in `docker/nginx/`.
- Persistent data (the database, static files and media) lives in the `/data` volume.

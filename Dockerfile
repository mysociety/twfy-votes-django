FROM python:3.11-bookworm
ENV INSIDE_DOCKER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_VERSION=1.8.0 \
    POETRY_VIRTUALENVS_CREATE=false \
    PYSETUP_PATH="/opt/pysetup"
RUN apt-get update && apt-get install -y \
    binutils libgdal-dev gdal-bin libproj-dev git npm \
    && rm -rf /var/lib/apt/lists/*
RUN curl -sSL https://install.python-poetry.org | python -
ENV PATH="/root/.local/bin:$PATH"
WORKDIR $PYSETUP_PATH
COPY poetry.loc[k] pyproject.toml ./
RUN poetry install --no-root

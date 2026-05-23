ARG PYTHON_VERSION=3.11
FROM python:${PYTHON_VERSION}-slim-buster

RUN apt-get update && \
    apt-get -y install git gcc g++ && \
    apt-get clean


WORKDIR /src


RUN pip3 install uv && \
    uv venv


CMD uv build
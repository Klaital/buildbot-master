FROM buildbot/buildbot-master:v2.7.0

LABEL maintainer="Kit Cox <chriscox@abandonedfactory.net>"

# docker commands
RUN pip install docker-py

RUN apk update \
    && apk add --virtual build-dependencies \
        build-base \
        gcc \
        wget \
        ca-certificates \
        bash \
    && apk add \
        openssh \
        python-dev

RUN pip install pip setuptools && \
    pip install --upgrade setuptools && \
    pip install treq && \
    pip install requests && \
    pip install confuse

# Avoid host key verification prompt for gitpoller
RUN echo "    StrictHostKeyChecking=no" >> /etc/ssh/ssh_config

WORKDIR /var/lib/buildbot
CMD ["dumb-init", "/usr/src/buildbot/docker/start_buildbot.sh"]

FROM debian:stretch

# Basic setup
RUN apt-get update \
    && apt-get install -y \
    build-essential \
    python3-dev \
    python3-pip \
    python3-cffi \
    python3-cryptography \
    libcairo2-dev \
    libgirepository1.0-dev \
    wget \
    supervisor \
    nano \
    git \
    curl \
    pkg-config

# Install redis for queueing
RUN curl -o /tmp/redis-stable.tar.gz http://download.redis.io/redis-stable.tar.gz \
  && cd /tmp \
  && tar -zxf redis-stable.tar.gz \
  && cd redis-stable \
  && make \
  && make install \
  && cp redis.conf /etc/redis.conf

# Pull the source code:
ARG appdir=/www
RUN mkdir ${appdir} \
  && git clone https://github.com/qbrc-cnap/biz_tier.git ${appdir}

# Install the python dependencies, as given from the repository:
RUN pip3 install --no-cache-dir -r "${appdir}"/requirements.txt
ENV APP_ROOT="${appdir}"

ENTRYPOINT ["/bin/bash"]

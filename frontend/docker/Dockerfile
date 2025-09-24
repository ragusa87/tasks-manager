FROM node:22-alpine

ARG USER_ID=1000
ARG GROUP_ID=1000

# Create a user with the specified UID/GID or use existing one
RUN if getent group ${GROUP_ID} >/dev/null 2>&1; then \
        EXISTING_GROUP=$(getent group ${GROUP_ID} | cut -d: -f1); \
    else \
        addgroup -g ${GROUP_ID} nodeuser; \
        EXISTING_GROUP=nodeuser; \
    fi; \
    if getent passwd ${USER_ID} >/dev/null 2>&1; then \
        EXISTING_USER=$(getent passwd ${USER_ID} | cut -d: -f1); \
    else \
        adduser -u ${USER_ID} -G $EXISTING_GROUP -D nodeuser; \
        EXISTING_USER=nodeuser; \
    fi

RUN mkdir -p /app/node_modules && chown -R ${USER_ID}:${GROUP_ID} /app
# Switch to the user with specified UID
USER ${USER_ID}:${GROUP_ID}

WORKDIR /app

FROM localhost/mcp-github-project-manager:latest

ENV NPM_CONFIG_CACHE=/tmp/.npm

USER root

RUN npm install -g mcp-proxy

RUN mkdir -p /app/.mcp-cache && chown 999:999 /app/.mcp-cache

USER 999

EXPOSE 8080

ENTRYPOINT ["mcp-proxy", "--port", "8080", "--server", "stream", "--", "node", "build/index.js"]

# inspeximus MCP server (agora-inspeximus) — zero-dependency agent memory over stdio MCP.
# Build:  docker build -t inspeximus-mcp .
# Run  :  docker run -i --rm inspeximus-mcp        # stdio transport; wire into any MCP client
FROM python:3.12-slim
WORKDIR /app
# install the published package with the MCP extra (zero-dependency core + the MCP server)
RUN pip install --no-cache-dir "agora-inspeximus[mcp]"
# stdio MCP server; responds to MCP introspection (tools/list) on start
ENTRYPOINT ["inspeximus-mcp"]

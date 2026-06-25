# Knowledge Graph Layer

## Purpose

The knowledge graph layer stores manufacturing entities and relationships in
Neo4j, then returns graph evidence that can be appended to agent responses.

It is deliberately separate from the API layer:

- API endpoints validate and orchestrate requests.
- `KnowledgeGraphService` owns Neo4j writes, read-only Cypher, and evidence formatting.
- `AgentOrchestrator` only consumes graph evidence and fails soft when Neo4j is unavailable.

## Endpoints

### `POST /api/v1/graph/entities`

Upserts one entity.

```json
{
  "entity_id": "equipment:CNC-001",
  "entity_type": "Equipment",
  "name": "CNC-001",
  "properties": {
    "line": "A"
  }
}
```

### `POST /api/v1/graph/relationships`

Upserts one relationship. Source and target entities must already exist.

```json
{
  "source_id": "sensor:vibration",
  "target_id": "equipment:CNC-001",
  "relationship_type": "MONITORS",
  "properties": {
    "threshold": 10
  }
}
```

### `POST /api/v1/graph/query`

Runs read-only Cypher. Write operations such as `CREATE`, `MERGE`, `SET`,
`DELETE`, and `DROP` are rejected.

```json
{
  "cypher": "MATCH (n:GraphEntity) RETURN n.id AS id, n.name AS name LIMIT 10",
  "parameters": {},
  "limit": 10
}
```

### `GET /api/v1/graph/evidence?query=CNC振动`

Returns graph evidence formatted for agent responses:

```text
[graph:Neo4j] CNC-001(Equipment) -[MONITORS]- 振动传感器(Sensor)
```

### `POST /api/v1/graph/demo/seed`

Writes a small manufacturing demo graph:

- equipment
- process
- defect
- sensor
- parameter
- material

## Orchestrator Integration

Agent evidence now has two retrieval layers:

- `[knowledge:...]` from local RAG.
- `[graph:Neo4j] ...` from Neo4j when available.

Neo4j failures do not block agent execution.

## Local Verification

Use the configured local Neo4j service:

```powershell
$env:NEO4J_ENABLED='true'
$env:NEO4J_URI='bolt://127.0.0.1:7687'
$env:NEO4J_USER='neo4j'
$env:NEO4J_PASSWORD='12345678'
python -c "from app.services.knowledge_graph_service import KnowledgeGraphService; print(KnowledgeGraphService().seed_demo_graph())"
```

If this returns `ServiceUnavailable`, start Neo4j first or use Docker Compose.

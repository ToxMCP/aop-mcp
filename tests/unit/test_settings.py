from src.server.config.settings import Settings


def test_settings_parse_csv_endpoints(monkeypatch) -> None:
    monkeypatch.setenv(
        "AOP_MCP_AOP_WIKI_SPARQL_ENDPOINTS",
        "https://one.example/sparql, https://two.example/sparql",
    )
    monkeypatch.setenv(
        "AOP_MCP_AOP_DB_SPARQL_ENDPOINTS",
        "https://db.example/sparql",
    )

    settings = Settings()

    assert settings.aop_wiki_sparql_endpoints == [
        "https://one.example/sparql",
        "https://two.example/sparql",
    ]
    assert settings.aop_db_sparql_endpoints == ["https://db.example/sparql"]

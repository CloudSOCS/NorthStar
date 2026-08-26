from agents.hypothesis_graph import DEFAULT_PATH, load_graph


def require_graph(path=None):
    return load_graph(path or DEFAULT_PATH)


def lessons_from_live_logs(path: str):
    require_graph()
    raise NotImplementedError(
        "post_mortem is a stub (cycle 1); ingest M1/M5 JSON via loop_controller instead"
    )

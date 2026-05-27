"""Page de recherche IA — endpoints pour /ai-search."""
import flask
import requests
from ckan.plugins import toolkit

CIOOS_AI_API = "http://host.docker.internal:8000"


def ai_search_page():
    """GET /ai-search — rendu de la page de recherche IA."""
    lang = toolkit.h.lang()

    try:
        stats_r = requests.get(f"{CIOOS_AI_API}/catalogue/stats", timeout=10)
        stats_r.raise_for_status()
        stats = stats_r.json()
    except Exception:
        stats = {"total": 0, "by_eov": {}, "by_org": {}, "by_format": {}}

    q = flask.request.args.get("q", "")

    return toolkit.render(
        "ai_search/index.html",
        extra_vars={"stats": stats, "lang": lang, "initial_q": q},
    )


def ai_search_query():
    """POST /ai-search/query — recherche sémantique directe (sans conversation)."""
    body    = flask.request.get_json(force=True) or {}
    query   = (body.get("query") or "").strip()
    filters = {k: v for k, v in (body.get("filters") or {}).items() if v}
    top_k   = int(body.get("top_k", 20))
    method  = body.get("method", "rerank")

    if not query and not filters:
        return flask.jsonify({"results": [], "total": 0, "time_ms": 0})

    try:
        r = requests.post(
            f"{CIOOS_AI_API}/search/{method}",
            json={"query": query or "ocean data", "top_k": top_k, "filters": filters},
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()

        results = data.get("results", [])
        for ds in results:
            ds["ckan_url"] = f"/dataset/{ds.get('name') or ds.get('id', '')}"

        return flask.jsonify({
            "results": results,
            "total":   data.get("total_candidates", len(results)),
            "time_ms": data.get("time_ms", 0),
            "method":  method,
            "query":   query,
        })

    except requests.Timeout:
        return flask.jsonify({"error": "timeout", "results": []}), 504
    except Exception as exc:
        return flask.jsonify({"error": str(exc), "results": []}), 500


def ai_search_compare():
    """POST /ai-search/compare — compare plusieurs méthodes sur la même requête."""
    body    = flask.request.get_json(force=True) or {}
    query   = (body.get("query") or "").strip()
    methods = body.get("methods", ["bm25", "dense", "rerank"])

    try:
        r = requests.post(
            f"{CIOOS_AI_API}/search/compare",
            json={"query": query, "top_k": 5, "methods": methods},
            timeout=60,
        )
        r.raise_for_status()
        return flask.jsonify(r.json())
    except Exception as exc:
        return flask.jsonify({"error": str(exc)}), 500

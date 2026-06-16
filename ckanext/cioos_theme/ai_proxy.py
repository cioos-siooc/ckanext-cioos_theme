"""Proxy CKAN → cioos-api pour le widget chat AI."""
import flask
import requests
from ckan.plugins import toolkit

# host.docker.internal permet à CKAN (dans Docker) d'atteindre cioos-api
# sur le port 8000 de la machine hôte
CIOOS_AI_API = "http://host.docker.internal:8000"


def _get_session_id():
    return flask.session.get("cioos_ai_session_id")


def _set_session_id(session_id):
    flask.session["cioos_ai_session_id"] = session_id
    flask.session.modified = True


def build_page_context():
    """Construit le contexte de la page côté serveur — plus fiable que le JS."""
    path = flask.request.path
    args = flask.request.args
    lang = toolkit.h.lang()

    ctx = {"url": path, "lang": lang}

    # Page de détail dataset
    if "/dataset/" in path and not args.get("eov") and not args.get("q"):
        pkg_name = path.split("/dataset/")[-1].strip("/")
        if pkg_name:
            try:
                pkg = toolkit.get_action("package_show")(
                    {"ignore_auth": True},
                    {"id": pkg_name},
                )
                ctx.update({
                    "type":          "dataset",
                    "dataset_id":    pkg.get("id", ""),
                    "dataset_name":  pkg.get("name", ""),
                    "dataset_title": (
                        (pkg.get("title_translated") or {}).get(lang)
                        or pkg.get("title", "")
                    ),
                    "organization":  ((pkg.get("organization") or {}).get("title", "")),
                    "eov_tags":      pkg.get("eov", []),
                })
            except Exception:
                ctx["type"] = "dataset"
        return ctx

    # Page de résultats / recherche
    if "/dataset" in path:
        ctx.update({
            "type":         "search",
            "eov_filter":   args.get("eov", ""),
            "org_filter":   args.get("organization", ""),
            "search_query": args.get("q", ""),
            "year_start":   args.get("ext_year_begin", ""),
            "year_end":     args.get("ext_year_end", ""),
        })
        try:
            fq_parts = []
            if ctx["eov_filter"]:
                fq_parts.append(f'eov:"{ctx["eov_filter"]}"')
            if ctx["org_filter"]:
                fq_parts.append(f'organization:{ctx["org_filter"]}')
            result = toolkit.get_action("package_search")(
                {"ignore_auth": True},
                {"q": ctx["search_query"], "fq": " AND ".join(fq_parts), "rows": 0},
            )
            ctx["result_count"] = result.get("count", 0)
        except Exception:
            pass
        return ctx

    # Page organisation
    if "/organization/" in path:
        org_name = path.split("/organization/")[-1].strip("/")
        ctx.update({
            "type":         "organization",
            "org_slug":     org_name,
            "search_query": args.get("q", ""),
            "year_start":   args.get("ext_year_begin", ""),
            "year_end":     args.get("ext_year_end", ""),
        })
        return ctx

    ctx["type"] = "home"
    return ctx


def _ensure_session(lang: str) -> str | None:
    """Retourne le session_id existant ou en crée un nouveau."""
    session_id = _get_session_id()
    if session_id:
        return session_id
    try:
        r = requests.post(
            f"{CIOOS_AI_API}/conversation/start",
            json={"lang": lang},
            timeout=10,
        )
        r.raise_for_status()
        session_id = r.json().get("session_id")
        _set_session_id(session_id)
        return session_id
    except Exception as exc:
        raise RuntimeError(f"Impossible de démarrer la session AI : {exc}") from exc


def ai_chat():
    """
    POST /api/ai/chat
    Corps : { "query": "..." }
    Proxifie vers cioos-api avec le contexte CKAN construit côté serveur.
    """
    if flask.request.method != "POST":
        return flask.jsonify({"error": "POST required"}), 405

    try:
        body = flask.request.get_json(force=True) or {}
    except Exception:
        return flask.jsonify({"error": "Invalid JSON"}), 400

    query = (body.get("query") or "").strip()
    if not query:
        return flask.jsonify({"error": "query required"}), 400

    page_context = build_page_context()
    lang = page_context.get("lang", "fr")

    try:
        session_id = _ensure_session(lang)
    except RuntimeError as exc:
        return flask.jsonify({"error": str(exc)}), 503

    try:
        r = requests.post(
            f"{CIOOS_AI_API}/conversation/{session_id}/message",
            json={"query": query, "page_context": page_context},
            timeout=90,
        )

        if r.status_code == 404:
            # Session expirée côté cioos-api → réinitialise et réessaie
            _set_session_id(None)
            session_id = _ensure_session(lang)
            r = requests.post(
                f"{CIOOS_AI_API}/conversation/{session_id}/message",
                json={"query": query, "page_context": page_context},
                timeout=90,
            )

        r.raise_for_status()
        data = r.json()
        data["page_context"] = page_context
        return flask.jsonify(data)

    except requests.Timeout:
        isFr = lang == "fr"
        return flask.jsonify({
            "response": (
                "La requête a pris trop de temps. Réessayez avec une question plus simple."
                if isFr else
                "The request timed out. Try a simpler question."
            ),
            "rag_mode":    "error",
            "dataset_list": [],
            "n_matching":  0,
            "action":      {"type": "none"},
        })
    except Exception as exc:
        return flask.jsonify({"error": str(exc)}), 500


def ai_session_reset():
    """POST /api/ai/reset — réinitialise la session AI côté serveur."""
    _set_session_id(None)
    return flask.jsonify({"ok": True})


def ai_feedback():
    """
    Proxy POST /api/ai/feedback → cioos-api/feedback/rate
    Évite le CORS — le JS appelle /api/ai/feedback
    (même origine CKAN) au lieu de localhost:8000 directement.
    """
    body = flask.request.get_json(force=True) or {}
    try:
        r = requests.post(
            f"{CIOOS_AI_API}/feedback/rate",
            json=body,
            timeout=5,
        )
        return flask.Response(
            r.content,
            status=r.status_code,
            mimetype="application/json",
        )
    except Exception as e:
        return flask.jsonify({"ok": False, "error": str(e)}), 500

"""Dataset views owned by the cioos plugin: DataCite XML, Responsible
organisations and lineage. URLs and endpoint names (cioos.*) are part of the
public contract."""

import ckan.lib.base as base
import ckan.model as model
import ckan.plugins.toolkit as toolkit
from ckan.views.dataset import GroupView
from ckantoolkit import _, g
from flask import Blueprint


def render_datacite_xml(id):
    context = {
        "model": model,
        "session": model.Session,
        "user": g.user,
        "for_view": True,
        "auth_user_obj": g.userobj,
    }
    data_dict = {"id": id}

    try:
        toolkit.check_access("package_update", context, data_dict)
    except toolkit.ObjectNotFound:
        toolkit.abort(404, _("Dataset not found"))
    except toolkit.NotAuthorized:
        toolkit.abort(
            403, _("User %r not authorized to view datacite xml for %s") % (g.user, id)
        )

    pkg = toolkit.get_action("package_show")(data_dict={"id": id})
    return toolkit.render("package/datacite.html", extra_vars={"pkg_dict": pkg})


def dataset_custom_GroupView(package_type, id):
    if toolkit.request.method == "POST":
        GroupView().post(package_type, id)
        return toolkit.h.redirect_to("cioos.resorg", package_type=package_type, id=id)

    context, pkg_dict = GroupView()._prepare(id)
    dataset_type = pkg_dict["type"] or package_type
    context["is_member"] = True
    users_groups = toolkit.get_action("group_list_authz")(context, {"id": id})

    pkg_group_ids = set(group["id"] for group in pkg_dict.get("groups", []))

    user_group_ids = set(group["id"] for group in users_groups)
    filtered_groups = toolkit.get_action("group_list")(
        context, data_dict={"type": "resorg"}
    )

    # filter groups by type
    pkg_dict["groups"] = [
        g for g in pkg_dict.get("groups", []) if g["name"] in filtered_groups
    ]
    group_dropdown = [
        [group["id"], group["display_name"]]
        for group in users_groups
        if group["id"] not in pkg_group_ids and group["name"] in filtered_groups
    ]

    for group in pkg_dict.get("groups", []):
        group["user_member"] = group["id"] in user_group_ids

    # TODO: remove
    # g.pkg_dict = pkg_dict
    # g.group_dropdown = group_dropdown

    return base.render(
        "package/group_list.html",
        {
            "dataset_type": dataset_type,
            "pkg_dict": pkg_dict,
            "group_dropdown": group_dropdown,
        },
    )


def dataset_custom_LineageView(package_type, id):
    context = {
        "model": model,
        "session": model.Session,
        "user": g.user,
        "for_view": True,
        "auth_user_obj": g.userobj,
    }
    data_dict = {"id": id, "include_tracking": False}

    # check if package exists
    try:
        pkg_dict = toolkit.get_action("package_show")(context, data_dict)
    except (toolkit.NotFound, toolkit.NotAuthorized):
        return base.abort(404, _("Dataset not found"))

    return base.render(
        "package/lineage.html",
        {"dataset_type": package_type, "pkg_dict": pkg_dict, "id": id},
    )


def get_blueprint():
    blueprint = Blueprint("cioos", __name__)
    blueprint.add_url_rule(
        "/dataset/<id>.dcxml", "datacite_xml", view_func=render_datacite_xml
    )
    blueprint.add_url_rule(
        "/<package_type>/resorg/<id>",
        "resorg",
        view_func=dataset_custom_GroupView,
        methods=["GET", "POST"],
    )
    blueprint.add_url_rule(
        "/<package_type>/lineage/<id>",
        "lineage",
        view_func=dataset_custom_LineageView,
        methods=["GET", "POST"],
    )
    return blueprint

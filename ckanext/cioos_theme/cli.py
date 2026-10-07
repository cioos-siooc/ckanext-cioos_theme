import json

import click
from ckan.plugins.toolkit import config


def get_commands():
    return [menu]


###########################################################################
# Sync Menu from wordpress
###########################################################################
@click.group()
def menu():
    """Generate a html menu snipit from an existing wordpress site"""
    pass


@menu.command("create")
@click.option(
    "--url",
    default=lambda: (
        config.get("ckan.site_home_url", config.get("ckan.site_home"))
        + "/wp-json/ra/menu/"
    ).replace("//", "/"),
    help="[ckan.site_home_url|ckan.site_home]/wp-json/ra/menu/",
)
@click.option(
    "--output", default="/menu/menu_list.html", help="path to menu list output file"
)
@click.option("--echo", default=False, help="echo file output to stdout")
def create_menu(url, output, echo):
    """create menu file from wordpress site"""

    import requests

    def process_list_item(menu_item, indent=2, parent_class=""):
        indent_str = " " * indent
        indent_str2 = " " * (indent + 2)
        out = ""
        if menu_item.get("sub_menu_items"):
            out += (
                indent_str
                + '<li class="menu-item menu-item-has-children %s">\n' % parent_class
            )
        else:
            out += indent_str + '<li class="menu-item">\n'
        out += (
            indent_str2
            + '<a href="%s"><span class="mega-indicator">%s</span></a>\n'
            % (menu_item["url"], menu_item["title"])
        )
        if menu_item.get("sub_menu_items"):
            out += indent_str2 + '<ul class="sub-menu">\n'
            for sub_menu_item in menu_item["sub_menu_items"]:
                out += process_list_item(sub_menu_item, indent + 4)
            out += indent_str2 + "</ul>\n"
        out += indent_str + "</li>\n"
        return out

    r_en = requests.get(url + "en")
    r_fr = requests.get(url + "fr")

    out_en = ""
    for menu_item in json.loads(r_en.content):
        out_en += process_list_item(menu_item, indent=4, parent_class="menu-parent")

    out_fr = ""
    for menu_item in json.loads(r_fr.content):
        out_fr += process_list_item(menu_item, indent=4, parent_class="menu-parent")

    content = "{%- if h.lang() == 'en' -%}\n"
    content += out_en
    content += "  {% else %}\n"
    content += out_fr
    content += "  {% endif %}\n"

    # Write the file to disk
    with open(
        "ckanext-cioos_theme/ckanext/cioos_theme/templates" + output, "w"
    ) as file:
        file.write(content)

    if echo:
        print(content)

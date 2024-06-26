import $ from "jquery";

import render_user_group_settings from "../templates/user_group_settings/user_group_settings.hbs";

import * as blueslip from "./blueslip";
import * as browser_history from "./browser_history";
import * as components from "./components";
import * as hash_util from "./hash_util";
import {$t} from "./i18n";
import {page_params} from "./page_params";
import * as people from "./people";
import * as settings_data from "./settings_data";
import * as ui from "./ui";
import * as user_group_ui_updates from "./user_group_ui_updates";
import * as user_groups from "./user_groups";
import * as user_group_settings_ui from "./user_groups_settings_ui";

export let toggler;
export let select_tab = "group_general_settings";

function setup_group_edit_hash(group) {
    const hash = hash_util.group_edit_url(group);
    browser_history.update(hash);
}

function get_user_group_id(target) {
    const $row = $(target).closest(".group-row");
    return Number.parseInt($row.attr("data-group-id"), 10);
}

function get_user_group_for_target(target) {
    const user_group_id = get_user_group_id(target);
    if (!user_group_id) {
        blueslip.error("Cannot find user group id for target");
        return undefined;
    }

    const group = user_groups.get_user_group_from_id(user_group_id);
    if (!group) {
        blueslip.error("get_user_group_for_target() failed id lookup: " + user_group_id);
        return undefined;
    }
    return group;
}

export function can_edit(group_id) {
    if (!settings_data.user_can_edit_user_groups()) {
        return false;
    }

    // Admins and moderators are allowed to edit user groups even if they
    // are not a member of that user group. Members can edit user groups
    // only if they belong to that group.
    if (page_params.is_admin || page_params.is_moderator) {
        return true;
    }

    return user_groups.is_direct_member_of(people.my_current_user_id(), group_id);
}

export function get_edit_container(group) {
    return $(`#groups_overlay .user_group_settings[data-group-id='${CSS.escape(group.id)}']`);
}

export function show_settings_for(node) {
    const group = get_user_group_for_target(node);
    const html = render_user_group_settings({
        group,
        can_edit: can_edit(group.id),
    });

    ui.get_content_element($("#user_group_settings")).html(html);
    user_group_ui_updates.update_toggler_for_group_setting(group);

    $("#user_group_settings .tab-container").prepend(toggler.get());
    const $edit_container = get_edit_container(group);
    $(".nothing-selected").hide();

    $edit_container.addClass("show");
}

export function setup_group_settings(node) {
    toggler = components.toggle({
        child_wants_focus: true,
        values: [
            {label: $t({defaultMessage: "General"}), key: "group_general_settings"},
            {label: $t({defaultMessage: "Members"}), key: "group_member_settings"},
        ],
        callback(name, key) {
            $(".group_setting_section").hide();
            $("." + key).show();
            select_tab = key;
        },
    });

    show_settings_for(node);
}

export function open_group_edit_panel_for_row(group_row) {
    const group = get_user_group_for_target(group_row);

    $(".group-row.active").removeClass("active");
    user_group_settings_ui.show_user_group_settings_pane.settings(group);
    $(group_row).addClass("active");
    setup_group_edit_hash(group);
    setup_group_settings(group_row);
}

export function initialize() {
    $("#manage_groups_container").on("click", ".group-row", function (e) {
        if ($(e.target).closest(".check, .user_group_settings_wrapper").length === 0) {
            open_group_edit_panel_for_row(this);
        }
    });
}

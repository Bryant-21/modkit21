import click

from cli._output import output


@click.group()
def manager():
    """Manage mod libraries and launch isolated game sessions."""


def report(ctx, operation, *args, **kwargs):
    from creation_lib.mod_manager.paths import ManagerError
    try:
        result = operation(*args, **kwargs)
    except (ManagerError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    output(result, ctx.obj["fmt"])


def library_options(function):
    function = click.option("--target", default="", help="Optional target ID within the selected profile.")(function)
    function = click.option("--profile", default="", help="Profile ID or unique name; defaults to the first profile.")(function)
    return click.option("--library", required=True, type=click.Path(exists=True))(function)


def read_json(text, label):
    import json
    try:
        return json.loads(text)
    except ValueError as exc:
        raise click.BadParameter("Use valid JSON.", param_hint=label) from exc


def run_actions(ctx, library, profile, target, steps, apply=False):
    from creation_lib.mod_manager.agent_launch import workflow
    report(ctx, workflow, library, profile, steps, target=target, apply=apply)


@manager.command("actions")
@click.pass_context
def actions(ctx):
    """List shared workflow actions, arguments, outputs, and mutation requirements."""
    from creation_lib.mod_manager.agent_launch import actions
    report(ctx, actions)


@manager.command("workflow")
@library_options
@click.option("--steps", default="", help='JSON action array, e.g. [{"action":"mods"}].')
@click.option("--file", "request_file", type=click.File("r", encoding="utf-8-sig"), help="Read the action array from a JSON file.")
@click.option("--apply", is_flag=True, help="Allow mutations; each action is its own transaction.")
@click.pass_context
def workflow(ctx, library, profile, target, steps, request_file, apply):
    """Run reviewed controller actions in one session; see manager actions for the contract."""
    if bool(steps) == bool(request_file):
        raise click.UsageError("Provide exactly one of --steps or --file.")
    run_actions(ctx, library, profile, target, read_json(request_file.read() if request_file else steps, "--steps/--file"), apply)


@manager.command("profiles")
@library_options
@click.argument("action", type=click.Choice(["list", "create", "clone", "rename", "delete", "restore", "backup"]), default="list")
@click.option("--name", default="")
@click.option("--id", "identifier", default="", help="Stable profile ID for delete/restore.")
@click.option("--apply", is_flag=True)
@click.pass_context
def profiles(ctx, library, profile, target, action, name, identifier, apply):
    """List or manage local profiles and metadata backups."""
    methods = {"list": ("profiles", []), "create": ("create_profile", [name]),
               "clone": ("create_profile", [name, True]), "rename": ("rename_profile", [name]),
               "delete": ("delete_profile", [identifier]), "restore": ("restore_profile", [identifier]),
               "backup": ("backup_profile", [])}
    method, args = methods[action]
    run_actions(ctx, library, profile, target, [{"action": method, "args": args}], apply)


@manager.command("mods")
@library_options
@click.argument("action", type=click.Choice(["list", "enable", "disable", "move", "organize", "edit", "uninstall", "restore", "undo"]), default="list")
@click.option("--mod", "mods", multiple=True, help="Stable mod ID; repeat for bulk changes.")
@click.option("--priority", type=click.IntRange(min=0), default=0)
@click.option("--changes", default="{}", help="JSON fields: organize accepts group/enabled/priority; edit accepts tags/notes/group/enabled.")
@click.option("--operation", default="", help="Recovery history operation ID for restore.")
@click.option("--apply", is_flag=True)
@click.pass_context
def mods(ctx, library, profile, target, action, mods, priority, changes, operation, apply):
    """List, organize, enable, uninstall, or recover mods through shared transactions."""
    if action in {"enable", "disable", "move", "organize", "edit", "uninstall"} and not mods:
        raise click.UsageError("Provide --mod for this action.")
    if action in {"enable", "disable", "move", "organize"}:
        options = {"enabled": action == "enable"} if action in {"enable", "disable"} else (
            {"priority": priority} if action == "move" else read_json(changes, "--changes"))
        steps = [{"action": "bulk_organize", "args": [list(mods)], "options": options}]
    elif action == "edit":
        steps = [{"action": "customize", "args": [mod], "options": read_json(changes, "--changes")} for mod in mods]
    elif action == "uninstall":
        steps = []
        for mod in mods:
            steps.append({"action": "review_owned", "args": [mod]})
            if apply:
                steps.append({"action": "uninstall"})
    elif action == "restore":
        steps = [{"action": "review_restore", "args": [operation]}]
        if apply:
            steps.append({"action": "restore"})
    else:
        steps = [{"action": "mods" if action == "list" else "undo_organization"}]
    run_actions(ctx, library, profile, target, steps, apply)


@manager.command("plugins")
@library_options
@click.option("--order", default="", help="Complete ordered plugin-name array as JSON.")
@click.option("--enabled", default="", help="Complete enabled plugin-name array as JSON.")
@click.option("--locked", default="", help="JSON array of [plugin, priority] locks.")
@click.option("--apply", is_flag=True)
@click.pass_context
def plugins(ctx, library, profile, target, order, enabled, locked, apply):
    """Inspect ESM/ESP/ESL headers and review dependency-checked plugin changes."""
    options = {key: read_json(text, "--" + key) for key, text in [("order", order), ("enabled", enabled), ("locked", locked)] if text}
    steps = [{"action": "review_plugins", "options": options}]
    if apply:
        steps.append({"action": "apply_plugins"})
    run_actions(ctx, library, profile, target, steps, apply)


@manager.command("files")
@library_options
@click.option("--archives", is_flag=True, help="Include archive providers and precedence diagnostics.")
@click.pass_context
def files(ctx, library, profile, target, archives):
    """Inspect file providers and conflicts."""
    run_actions(ctx, library, profile, target, [{"action": "inspect_combined_data" if archives else "inspect_files"}])


@manager.command("saves")
@library_options
@click.option("--global", "global_saves", is_flag=True, help="Read the game's shared Documents saves.")
@click.option("--folder", default=None, type=click.Path(exists=True, file_okay=False))
@click.option("--inspect", default="", help="Read a listed save's header and plugin dependencies.")
@click.pass_context
def saves(ctx, library, profile, target, global_saves, folder, inspect):
    """List save files, optionally inspect one; transfers are available through workflow."""
    if folder and global_saves:
        raise click.UsageError("Choose --folder or --global.")
    steps = [{"action": "inspect_source_saves", "args": [folder]}] if folder else [
        {"action": "inspect_global_saves" if global_saves else "inspect_saves"}]
    if inspect:
        steps.append({"action": "inspect_save_plugins", "args": [inspect]})
    run_actions(ctx, library, profile, target, steps)


@manager.command("executables")
@library_options
@click.argument("action", type=click.Choice(["list", "save", "remove"]), default="list")
@click.option("--definition", default="{}", help="Executable fields as JSON: id, title, binary, arguments, working_directory, mode, instance_id.")
@click.option("--id", "identifier", default="")
@click.option("--apply", is_flag=True)
@click.pass_context
def executables(ctx, library, profile, target, action, definition, identifier, apply):
    """Manage the executable definitions shared by UI and CLI launches."""
    step = {"action": "executables"} if action == "list" else (
        {"action": "save_executable", "options": read_json(definition, "--definition")} if action == "save" else
        {"action": "remove_executable", "args": [identifier]})
    run_actions(ctx, library, profile, target, [step], apply)


@manager.command("targets")
@library_options
@click.option("--name", default="")
@click.option("--game-root", default=None, type=click.Path(exists=True, file_okay=False))
@click.option("--id", "identifier", default="", help="Existing target to update; blank creates a new target.")
@click.option("--apply", is_flag=True)
@click.pass_context
def targets(ctx, library, profile, target, name, game_root, identifier, apply):
    """List targets, or review/apply a dynamically selected game directory."""
    steps = [{"action": "targets"}] if not game_root else [
        {"action": "review_target", "args": [name, game_root, identifier]}]
    if game_root and apply:
        steps.append({"action": "apply_target", "options": {"automatic": False}})
    run_actions(ctx, library, profile, target, steps, apply)


@manager.command("updates")
@library_options
@click.option("--check", is_flag=True, help="Check the next due batch, respecting saved progress and backoff.")
@click.option("--files", is_flag=True, help="Include published file replacements and account state.")
@click.pass_context
def updates(ctx, library, profile, target, check, files):
    """Reconnect the saved account and report cached update results and schedule."""
    run_actions(ctx, library, profile, target, [{"action": "updates", "options": {"check": check, "files": files}}])


@manager.command("downloads")
@library_options
@click.argument("action", type=click.Choice(["list", "download", "resume", "remove"]), default="list")
@click.option("--nxm", default="", help="Fresh nxm:// request for a download.")
@click.option("--id", "identifier", default="", help="Download job ID for resume/remove.")
@click.option("--apply", is_flag=True)
@click.pass_context
def downloads(ctx, library, profile, target, action, nxm, identifier, apply):
    """Inspect the durable queue, fetch an NXM request, resume, or remove a job."""
    method = {"list": "downloads", "download": "download", "resume": "resume_download", "remove": "remove_download_job"}[action]
    args = [] if action == "list" else [nxm if action == "download" else identifier]
    run_actions(ctx, library, profile, target, [{"action": method, "args": args}], apply)


@manager.command("instances")
@click.option("--root", type=click.Path(path_type=str))
@click.pass_context
def instances(ctx, root):
    """List available MO2 instances without changing them."""
    from creation_lib.mod_manager.agent_launch import instances
    report(ctx, instances, root)


@manager.command("create-instance")
@click.option("--library", required=True, type=click.Path())
@click.option("--game", default="fo4")
@click.option("--game-root", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--name", default="Default")
@click.pass_context
def create_instance(ctx, library, game, game_root, name):
    """Create a standalone game library/profile without importing MO2."""
    from creation_lib.mod_manager.agent_launch import create_instance
    report(ctx, create_instance, library, game, game_root, name)


@manager.command("install")
@click.option("--library", required=True, type=click.Path(exists=True))
@click.option("--profile", required=True)
@click.option("--package", required=True, type=click.Path(exists=True))
@click.option("--name", default="")
@click.option("--choices", default="{}", help="JSON object of FOMOD group IDs to option IDs; IDs appear in the preview.")
@click.option("--manual", is_flag=True)
@click.option("--root", default="", help="Data root within a manual package layout.")
@click.option("--replace", default="", help="Owned mod ID to reinstall.")
@click.option("--overlay", default="", help="Referenced mod ID to place an owned additive update above.")
@click.option("--target", default="", help="Target ID to use for installer dependency context.")
@click.option("--policy", type=click.Choice(["mo2", "schema"]), default="mo2")
@click.option("--disabled", is_flag=True, help="Install without enabling the new mod.")
@click.option("--adjustments", default="{}", help="JSON objects for mapping, additions and repairs; uses the UI's file-review rules.")
@click.option("--mode", type=click.Choice(["replace", "merge"]), default="replace")
@click.option("--expect", default="", help="Require the review token from a previous preview.")
@click.option("--apply", is_flag=True, help="Install the reviewed selection; otherwise preview only.")
@click.pass_context
def install(ctx, library, profile, package, choices, adjustments, **options):
    """Preview installer choices and files, then explicitly install into the library."""
    import json
    from creation_lib.mod_manager.agent_launch import install
    try:
        selection = json.loads(choices)
    except ValueError as exc:
        raise click.BadParameter("Use a JSON object for choices.", param_hint="--choices") from exc
    report(ctx, install, library, profile, package, choices=selection, adjustments=read_json(adjustments, "--adjustments"), **options)


@manager.command("create-mod")
@click.option("--library", required=True, type=click.Path(path_type=str))
@click.option("--profile", required=True)
@click.option("--after", default="", help="Insert below this mod ID; otherwise append.")
@click.argument("name")
@click.pass_context
def create_mod(ctx, library, profile, after, name):
    """Create an empty owned mod folder in a profile."""
    from creation_lib.mod_manager.agent_launch import empty_mod
    report(ctx, empty_mod, library, profile, name, after)


@manager.command("sync")
@click.option("--mo2", required=True, type=click.Path(exists=True))
@click.option("--library", required=True, type=click.Path())
@click.pass_context
def sync(ctx, mo2, library):
    """Import or refresh an MO2 instance into a local library."""
    from creation_lib.mod_manager.agent_launch import sync
    report(ctx, sync, mo2, library)


@manager.command("archives")
@click.option("--library", required=True, type=click.Path(exists=True))
@click.option("--profile", required=True)
@click.option("--archive", default="", help="Exact container path or unique name for a preview.")
@click.option("--member", default="", help="Preview this member without extracting files to disk.")
@click.option("--target", default="", help="Inspect archives for this launch target.")
@click.pass_context
def archives(ctx, library, profile, archive, member, target):
    """List archive providers and members, or read a bounded member preview."""
    from creation_lib.mod_manager.agent_launch import archives
    report(ctx, archives, library, profile, archive, member, target)


@manager.command("launch")
@click.option("--library", required=True, type=click.Path(exists=True))
@click.option("--profile", required=True)
@click.option("--exe", "executable", default="f4se", show_default=True)
@click.option("--mcp-port", type=click.IntRange(1, 65535), help="Omit to allocate a free per-session port.")
@click.option("--disable-mcp", is_flag=True, help="Keep B21_MCP disabled for this launch; allocate no port.")
@click.option("--isolate-documents/--shared-documents", default=None, help="Override the saved Documents mode; shared is the default.")
@click.option("--ini", "overrides", multiple=True, help="FILE:SECTION:KEY=VALUE")
@click.option("--ini-source", type=click.Choice(["auto", "profile", "global"]), default="auto")
@click.option("--agent-defaults", is_flag=True)
@click.option("--accept-minimal-ini", is_flag=True)
@click.option("--wait-game", type=click.FloatRange(min=0), default=0.0)
@click.option("--dry-run", is_flag=True)
@click.pass_context
def launch(ctx, **options):
    """Launch a profile with its own VFS, output folders and MCP port."""
    from creation_lib.mod_manager.agent_launch import launch
    options["library_root"] = options.pop("library")
    report(ctx, launch, **options)


@manager.command("categories")
@click.option("--library", required=True, type=click.Path(exists=True))
@click.option("--game", default="fallout4", show_default=True)
@click.option("--refresh", is_flag=True, help="Fetch the full Nexus catalog.")
@click.option("--import", "merge", is_flag=True, help="Merge catalog entries into local categories.")
@click.pass_context
def categories(ctx, library, game, refresh, merge):
    """Read the cached category hierarchy or refresh/import it from Nexus."""
    from creation_lib.mod_manager.agent_launch import categories
    report(ctx, categories, library, game, refresh, merge)


@manager.group("nexus")
def nexus():
    """Sign in to the Nexus account shared with the UI."""


@nexus.command("login")
@click.option("--saved", is_flag=True, help="Validate the securely stored credential.")
@click.option("--remember/--session", default=True, help="Save a validated key in Windows Credential Manager.")
@click.pass_context
def nexus_login(ctx, saved, remember):
    from creation_lib.mod_manager.agent_launch import nexus_auth
    key = "" if saved else click.prompt("Nexus API key", hide_input=True)
    report(ctx, nexus_auth, "login", key, remember)


@nexus.command("logout")
@click.pass_context
def nexus_logout(ctx):
    """Remove the saved credential."""
    from creation_lib.mod_manager.agent_launch import nexus_auth
    report(ctx, nexus_auth, "logout")


@nexus.command("status")
@click.pass_context
def nexus_status(ctx):
    """Report whether a saved credential exists, without exposing it."""
    from creation_lib.mod_manager.agent_launch import nexus_auth
    report(ctx, nexus_auth, "status")


@manager.command("status")
@click.option("--library", required=True, type=click.Path(exists=True))
@click.option("--session", default="")
@click.pass_context
def status(ctx, library, session):
    """Show session process identities, output paths and MCP endpoints."""
    from creation_lib.mod_manager.agent_launch import status
    report(ctx, status, library, session)


@manager.command("launch-options")
@click.option("--library", required=True, type=click.Path(exists=True))
@click.option("--profile", required=True)
@click.option("--isolate-documents/--shared-documents", default=None)
@click.pass_context
def launch_options(ctx, library, profile, isolate_documents):
    """Read or save profile launch options shared with the UI."""
    from creation_lib.mod_manager.agent_launch import launch_options
    report(ctx, launch_options, library, profile, isolate_documents)


@manager.command("stop")
@click.option("--library", required=True, type=click.Path(exists=True))
@click.option("--pid", required=True, type=click.IntRange(min=1))
@click.option("--timeout", type=click.FloatRange(min=0), default=30.0)
@click.pass_context
def stop(ctx, library, pid, timeout):
    """Stop only the verified process belonging to this library."""
    from creation_lib.mod_manager.agent_launch import stop
    report(ctx, stop, library, pid, timeout=timeout)


@manager.command("import-saves")
@click.option("--library", required=True, type=click.Path(exists=True))
@click.option("--profile", required=True)
@click.option("--folder", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--save", "names", multiple=True)
@click.option("--latest", is_flag=True)
@click.pass_context
def import_saves(ctx, library, profile, folder, names, latest):
    """Carry selected session saves into the baseline for future launches."""
    from creation_lib.mod_manager.agent_launch import import_saves
    report(ctx, import_saves, library, profile, names, folder=folder, latest=latest)

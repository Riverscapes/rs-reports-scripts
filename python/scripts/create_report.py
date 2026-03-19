"""Interactive CLI script: create and run a Riverscapes Report end-to-end.

This script walks you through every step needed to produce a report, asking
questions at each stage so you do not need to write any code.

Run this script using the launch menu under "🐍 Python: Run/Debug Current File".  You will
be prompted to select which API stage to target (staging or production), then you will be 
guided through the workflow described below.

Workflow
--------
1. **Authenticate** \u2014 a browser tab opens for you to log in with your
   Riverscapes account (OAuth 2.0 PKCE flow).  The token is cached for the
   duration of the script.
2. **Pick a report type** \u2014 only types that support the ``PICK`` input
   tool are shown (i.e. those that need you to select an existing geographic
   feature rather than draw or upload one).
3. **Name the report** \u2014 a default name with a timestamp is pre-filled.
4. **Select a picker layer** \u2014 if the report type declares ``validPickerLayers``,
   you choose which layer to select from (e.g. ``huc``, ``catchment``).
5. **Enter a picker item ID** \u2014 the ID of the specific feature in the chosen
   layer (e.g. a HUC-12 code like ``1302020710``).
6. **Choose a unit system** \u2014 if the report type supports multiple unit systems
   (e.g. ``SI`` / ``imperial``), you pick one.
7. **Create the report** \u2014 a ``CREATED`` record is registered in the API and
   an ID is returned.
8. **Attach picker option** \u2014 the chosen layer + ID is linked to the report.
9. **Start the report** \u2014 the report is submitted to the processing queue.
10. **Poll for completion** \u2014 the script checks the status every 10 seconds
    and prints progress until the report reaches a terminal state.
11. **Print a link** \u2014 on success a direct URL to the finished report is shown.

Usage
-----
::

    python scripts/create_report.py staging
    python scripts/create_report.py production

Arguments
---------
stage : {'staging', 'production', 'local'}
    Which API environment to target.  Use ``staging`` while developing;
    use ``production`` for real work.
"""
from datetime import datetime
import argparse
import questionary
from rsxml import Logger
from termcolor import colored
from pyreports import ReportsAPI

log = Logger('Create Report')


def layer_label(layer_id: str) -> str:
    """Convert a picker layer ID to a human-readable label."""
    return layer_id.replace('_', ' ').title()


def main():
    """Entry point for the interactive report-creation CLI.

    Parses the ``stage`` positional argument, authenticates with the API,
    and walks the user through a series of ``questionary`` prompts to
    configure and launch a report.  Blocks until the report reaches a
    terminal state, then prints a summary and (on success) a direct URL
    to view the report on the Riverscapes Reports web frontend.
    """
    parser = argparse.ArgumentParser(description="Create and run a report interactively.")
    parser.add_argument('stage', choices=['staging', 'production', 'local'], help="API stage")
    args = parser.parse_args()

    with ReportsAPI(stage=args.stage) as api:
        log.title(f"🚀 Creating report on {args.stage.upper()}")

        ################## API CALL: List report types and pick one ##################
        report_types = api.list_report_types()

        # Filter out anything that doesn't have PickToolsEnum.PICK inside parameters.tools.
        # This tool currently doesn't support DRAW or UPLOAD (but it couls)
        report_types_filtered = [x for x in report_types if 'PICK' in (x.parameters or {}).get('tools', [])]
        report_type = questionary.select(
            "Select report type:",
            choices=[
                questionary.Choice(f"{rt.name}  (v{rt.version})", value=rt)
                for rt in report_types_filtered
            ],
        ).ask()
        if report_type is None:
            return

        # Enter a report name, set the default to be just the report type name with a timestamp, but allow the user to change it.
        name = questionary.text(
            "Report name:",
            validate=lambda v: "Name cannot be empty" if not v.strip() else True,
            default=f"{report_type.name} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        ).ask()
        if name is None:
            return

        # Pick a picker layer (if the report type defines any)
        picker_layer = None
        valid_layers = (report_type.parameters or {}).get('validPickerLayers', [])
        if valid_layers:
            picker_layer = questionary.select("Select picker layer:", choices=[
                questionary.Choice(layer_label(layer), value=layer)
                for layer in valid_layers
            ],
            ).ask()
            if picker_layer is None:
                return

        # Now we have to enter an ID as a string that corresponds to the id of the object in the picker layer
        picker_id = None
        if picker_layer:
            picker_id = questionary.text(f"Enter ID for {layer_label(picker_layer)}:", default='1302020710').ask()
            if picker_id is None:
                return

        parameters = {}
        # If validUnitSystems is defined inside tool type parmaters then we need to choose from the opsions       validUnitSystems: ['SI', 'imperial'], // Remove this property if UNITS is not a valid parameter for this report ORDER IS PRESENTATION ORDER. FIRST ITEM IS THE DEFAULT
        valid_unit_systems = (report_type.parameters or {}).get('validUnitSystems', [])
        if valid_unit_systems:
            parameters['units'] = questionary.select("Select unit system:", choices=[
                questionary.Choice(unit_system.upper(), value=unit_system)
                for unit_system in valid_unit_systems
            ]).ask()

        #################### API CALL: Create report ##################
        # We create an empty report in order to have an id we can attach our input geojson to
        report = api.create_report(
            name=name.strip(),
            report_type_id=report_type.id,
            parameters=parameters,
        )
        log.info(colored(f"✅ Report created: {report.id}", 'green'))
        log.info(f"  📛 Name:   {report.name}")
        log.info(f"  📊 Status: {report.status}")
        log.info(f"  📋 Type:   {report.report_type.name if report.report_type else report_type.id}")

        # Attach the picker option (if a picker layer was selected)
        if picker_layer and picker_id:
            log.info(f"📎 Attaching picker option: {layer_label(picker_layer)} = {picker_id}")

            #################### API CALL: Attach picker option to report ##################
            api.attach_picker_option(report.id, picker_layer, picker_id)

            log.info(colored("✅ Picker option attached.", 'green'))

        # Start the report
        log.info(colored("▶️  Starting report...", 'cyan'))

        ##################### API CALL: Start report ##################
        report = api.start_report(report.id)
        log.info(colored(f"🔄 Report started (status: {report.status})", 'cyan'))

        # Poll every 10 seconds until a terminal state is reached
        log.info(colored("⏳ Polling for completion every 10 seconds...", 'cyan'))

        ##################### API CALL: Poll report ##################
        report = api.poll_report(report.id, interval=10)

        print()
        if report.is_complete():
            log.info(colored("🎉 Report COMPLETE!", 'green'))
            frontend_urls = {
                'production': 'https://reports.riverscapes.net',
                'staging': 'https://staging.reports.riverscapes.net',
            }
            base = frontend_urls.get(args.stage)
            if base and report.created_by_id:
                print(colored(f"  🔗 View report: {base}/reports/{report.created_by_id}/{report.id}/report.html", 'green'))
            elif base:
                print(colored(f"  🔗 View your reports: {base}/my", 'green'))
        else:
            log.error(colored(f"❌ Report ended with status: {report.status}", 'red'))
            if report.status_message:
                log.error(f"  💬 Message: {report.status_message}")
        print(f"  Report ID: {report.id}")
        print()


if __name__ == '__main__':
    main()

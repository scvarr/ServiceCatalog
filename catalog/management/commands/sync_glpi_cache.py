from django.core.management.base import BaseCommand, CommandError

from catalog.glpi_cache import sync_glpi_cache
from catalog.models import GlpiCacheSyncRun


class Command(BaseCommand):
    help = "Synchronize the local GLPI cache and linked catalog instances."

    def add_arguments(self, parser):
        parser.add_argument("--no-linked-instances", action="store_true")
        parser.add_argument("--page-size", type=int, default=None)
        parser.add_argument("--component-workers", type=int, default=None)
        parser.add_argument("--fail-on-partial", action="store_true")

    def handle(self, *args, **options):
        run = sync_glpi_cache(trigger=GlpiCacheSyncRun.Trigger.COMMAND, page_size=options["page_size"], component_workers=options["component_workers"], refresh_linked=not options["no_linked_instances"])
        self.stdout.write(f"GLPI cache run {run.pk}: {run.status}; {run.statistics}")
        if run.status == GlpiCacheSyncRun.Status.FAILED or (options["fail_on_partial"] and run.status == GlpiCacheSyncRun.Status.PARTIAL):
            raise CommandError(run.error_summary or "GLPI cache synchronization did not complete.")


from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from pretalx.person.models import User

from ... import models


class Command(BaseCommand):
    help = 'Mandatory emails to ticket holders, contains an unsubscribe option if they receive the newsletter but don\'t have a ticket'

    def add_arguments(self, parser):
        parser.add_argument('email_name', type=str)
        parser.add_argument(
            '--danger-all-active-users',
            action='store_true',
            dest='allusers',
            help="Dangerous: Emails all active users, also users without tickets (includes un-accepted speakers)",
        )
        parser.add_argument(
            '--active-ticketholders',
            action='store_true',
            dest='registered',
            help="Only active ticket-holders",
        )
        parser.add_argument(
            '--inactive-ticketholders',
            action='store_true',
            dest='unregistered',
            help="Only active ticket-holders",
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            dest='reset',
            help="Resets all before sending (force resend)",
        )
        parser.add_argument(
            '--newsletter',
            action='store_true',
            dest='newsletter',
            help="Sends to all newsletter recipients",
        )
        parser.add_argument(
            '--users',
            action='store_true',
            dest='users',
            help="Sends to users (default: ticketholders)",
        )
        parser.add_argument(
            '--test-to',
            type=str,
            dest='test',
            help="Sends to a test email and does not fetch recipients from db",
        )

    def handle(self, *args, **options):  # noqa:max-complexity=11

        try:
            email_template = models.EmailTemplate.objects.get(name=options['email_name'])
        except models.EmailTemplate.DoesNotExist:
            raise CommandError("Email '{}' not found".format(options['email_name']))

        users = User.objects.filter(is_active=True)

        if options['reset']:
            # This deletes rather than updates, because the recipient list could
            # have changed
            email_template.recipients.all().delete()

        if not options['allusers']:
            users = users.exclude(tickets=None)

        # Forgot about YAGNI here..
        if options['unregistered']:
            users = users.filter(Q(password__startswith='!') | Q(password__isnull=True))
        if options['registered']:
            users = users.exclude(Q(password__startswith='!') | Q(password__isnull=True))

        emails = set()

        if options['users']:
            self.stdout.write(self.style.WARNING("Sending to {} users".format(users.count())))
            for u in users:
                emails.add(u.email.lower())
        else:
            self.stdout.write(self.style.WARNING("Not sending to any users"))

        # ALWAYS keep active staff in the loop
        for admin in User.objects.filter(is_active=True, is_staff=True):
            emails.add(admin.email.lower())

        no_unsubscribe = emails.copy()

        if options['newsletter']:
            self.stdout.write(self.style.WARNING("Sending to newsletter recipients as well"))
            for subscriber in models.Subscription.objects.filter(confirmed=True):
                emails.add(subscriber.email.lower())

        if options['test']:
            self.stdout.write(self.style.WARNING("Sending just a test to: {}".format(options['test'])))
            no_unsubscribe = set()
            emails = set()
            emails.add(options['test'])

        if input("Continue? [y/N] ").lower().strip() != "y":
            return

        email_template.populate_recipients(emails)

        sent = 0

        for recipient in email_template.recipients.filter(sent=False):

            unsubscribe = recipient.email in no_unsubscribe and options['newsletter']
            email_template.send(recipient, unsubscribe=unsubscribe)
            sent += 1

        self.stdout.write(self.style.SUCCESS("Sent to {} new users".format(sent)))

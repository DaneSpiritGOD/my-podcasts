# Omit itunes:block and podcast:locked

The feed carries neither `itunes:block` nor `podcast:locked`. Directory inclusion requires actively submitting the feed URL to Apple, which we never do, so blocking defends against a scenario we do not trigger. Meanwhile `podcast:locked = yes` instructs every platform to reject the feed outright — including the manual "Follow a Show by URL" flow that is the entire subscription mechanism here.

## Consequences

The failure modes are asymmetric: wrongly locking ourselves out ends the project, while a feed we never submitted appearing in a directory is not a thing that happens on its own. If extra protection is ever wanted, adding the tags later is a one-line change that takes effect on the next refresh.

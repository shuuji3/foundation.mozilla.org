from django.conf import settings
from django.contrib.syndication.views import Feed
from django.core.cache import cache
from django.utils.feedgenerator import Atom1Feed

from networkapi.wagtailpages.utils import get_locale_from_request

from .models import IndexPage


class RSSFeed(Feed):
    """
    Blog page RSS feed, using the content:encoded serializer above
    """

    title = "Mozilla Foundation Blog"
    link = "https://foundation.mozilla.org/blog/"
    feed_url = "https://foundation.mozilla.org/blog/rss/"
    description = "The Mozilla Foundation Blog"

    def __call__(self, request, *args, **kwargs):
        # get locale from request header, or fall back to the default EN locale.
        request_locale = get_locale_from_request(request)
        setattr(self, "request_locale", request_locale)
        return super().__call__(request, *args, **kwargs)

    def items(self):
        # Get locale from request in __call__ above, defaults to EN.
        request_locale = getattr(self, "request_locale")

        # Try to get the RSS items from cache first
        feed_set = cache.get("rss_feed_set")

        if feed_set is None:
            # If we don't have an active cache, we build one: pull the index page
            # specifically using the English page title, as an IndexPage rather than
            # as a BlogIndexPage, to make sure we're not filtering out all the
            # "featured" posts (which we need to do for site content purposes).
            try:
                index = IndexPage.objects.get(title__iexact="Blog", locale=request_locale)

            except IndexPage.DoesNotExist:
                # If that doesn't yield the blog page, pull using the universal title
                try:
                    index = IndexPage.objects.get(title__iexact="Blog", locale=request_locale)

                except IndexPage.DoesNotExist:
                    # At this point there's not much we can do other than to pretend
                    # there are no posts to serialize to RSS/Atom format.
                    return []

            # Then sort the collection and only yield the top FEED_LIMIT posts
            blog_pages = index.get_all_entries(request_locale).order_by("-first_published_at")
            feed_set = blog_pages[: settings.FEED_LIMIT]

            cache.set("rss_feed_set", feed_set, settings.FEED_CACHE_TIMEOUT)

        return feed_set

    def item_title(self, item):
        return item.title

    def item_link(self, item):
        return item.full_url

    def item_description(self, item):
        return item.specific.get_meta_description()

    def item_pubdate(self, item):
        return item.first_published_at


class AtomFeed(RSSFeed):
    feed_type = Atom1Feed
    link = RSSFeed.link
    feed_url = "https://foundation.mozilla.org/blog/atom/"
    subtitle = RSSFeed.description

import json
import re
import typing

from bs4 import BeautifulSoup
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import int_list_validator
from django.db import Error, models
from django.db.models import F
from django.http import (
    HttpResponse,
    HttpResponseNotAllowed,
    HttpResponseNotFound,
    HttpResponseServerError,
)
from django.templatetags.static import static
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext
from modelcluster import models as cluster_models
from modelcluster.fields import ParentalKey
from wagtail.admin.edit_handlers import (
    FieldPanel,
    InlinePanel,
    MultiFieldPanel,
    PageChooserPanel,
)
from wagtail.core.fields import RichTextField
from wagtail.core.models import Orderable, Page, TranslatableMixin
from wagtail.images.edit_handlers import ImageChooserPanel
from wagtail.search import index
from wagtail.snippets.edit_handlers import SnippetChooserPanel
from wagtail.snippets.models import register_snippet
from wagtail_airtable.mixins import AirtableMixin
from wagtail_localize.fields import SynchronizedField, TranslatableField

from networkapi.utility import orderables
from networkapi.wagtailpages.fields import ExtendedYesNoField
from networkapi.wagtailpages.pagemodels.buyersguide.forms import (
    BuyersGuideProductCategoryForm,
)
from networkapi.wagtailpages.pagemodels.buyersguide.utils import (
    get_buyersguide_featured_cta,
    get_categories_for_locale,
)
from networkapi.wagtailpages.pagemodels.customblocks.base_rich_text_options import (
    base_rich_text_options,
)
from networkapi.wagtailpages.pagemodels.mixin.foundation_metadata import (
    FoundationMetadataPageMixin,
)
from networkapi.wagtailpages.pagemodels.mixin.snippets import LocalizedSnippet
from networkapi.wagtailpages.utils import (
    TitleWidget,
    get_language_from_request,
    get_original_by_slug,
    insert_panels_after,
)

if typing.TYPE_CHECKING:
    from networkapi.wagtailpages.models import BuyersGuideArticlePage


TRACK_RECORD_CHOICES = [
    ("Great", "Great"),
    ("Average", "Average"),
    ("Needs Improvement", "Needs Improvement"),
    ("Bad", "Bad"),
]


@register_snippet
class BuyersGuideProductCategory(
    index.Indexed,
    TranslatableMixin,
    LocalizedSnippet,
    # models.Model
    cluster_models.ClusterableModel,
):
    """
    A simple category class for use with Buyers Guide products,
    registered as snippet so that we can moderate them if and
    when necessary.
    """

    name = models.CharField(max_length=100)

    description = models.TextField(
        max_length=300,
        help_text="Description of the product category. Max. 300 characters.",
        blank=True,
    )

    parent = models.ForeignKey(
        "wagtailpages.BuyersGuideProductCategory",
        related_name="+",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        help_text="Leave this blank for a top-level category, or pick another category to nest this under",
    )

    featured = models.BooleanField(
        default=False,
        help_text="Featured category will appear first on Buyer's Guide site nav",
    )

    hidden = models.BooleanField(
        default=False,
        help_text="Hidden categories will not appear in the Buyer's Guide site nav at all",
    )

    slug = models.SlugField(
        blank=True,
        help_text="A URL-friendly version of the category name. This is an auto-generated field.",
        max_length=100,
    )

    sort_order = models.IntegerField(
        default=1,
        help_text="Sort ordering number. Same-numbered items sort alphabetically",
    )

    share_image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name="Share Image",
        help_text="Optional image that will apear when category page is shared.",
    )

    show_cta = models.BooleanField(
        default=False,
        help_text="Do we want the Buyers Guide featured CTA to be displayed on this category's page?",
    )

    panels = [
        FieldPanel(
            "name",
            widget=TitleWidget(attrs={"class": "max-length-warning", "data-max-length": 50}),
        ),
        FieldPanel("description"),
        SnippetChooserPanel("parent"),
        FieldPanel("featured"),
        FieldPanel("hidden"),
        FieldPanel("sort_order"),
        ImageChooserPanel("share_image"),
        FieldPanel("show_cta"),
        InlinePanel(
            "related_article_relations",
            heading="Related articles",
            label="Article",
            max_num=6,
        ),
    ]

    translatable_fields = [
        TranslatableField("name"),
        TranslatableField("description"),
        TranslatableField("related_article_relations"),
        SynchronizedField("slug"),
        SynchronizedField("share_image"),
        SynchronizedField("parent"),
    ]

    @property
    def published_product_page_count(self):
        return ProductPage.objects.filter(product_categories__category=self).live().count()

    def get_parent(self):
        return self.parent

    def get_children(self):
        return BuyersGuideProductCategory.objects.filter(parent=self)

    def get_related_articles(self) -> list["BuyersGuideArticlePage"]:
        return orderables.get_related_items(
            self.related_article_relations.all(),
            "article",
        )

    def get_primary_related_articles(self) -> list["BuyersGuideArticlePage"]:
        return self.get_related_articles()[:3]

    def get_secondary_related_articles(self) -> list["BuyersGuideArticlePage"]:
        return self.get_related_articles()[3:]

    def __str__(self):
        if self.parent is None:
            return f"{self.name} (sort order: {self.sort_order})"
        return f"{self.parent.name}: {self.name} (sort order: {self.sort_order})"

    def save(self, *args, **kwargs):
        self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    base_form_class = BuyersGuideProductCategoryForm

    search_fields = [
        index.SearchField("name", partial_match=True),
        index.FilterField("locale_id"),
    ]

    class Meta(TranslatableMixin.Meta):
        verbose_name = "Buyers Guide Product Category"
        verbose_name_plural = "Buyers Guide Product Categories"
        ordering = [
            F("parent__sort_order").asc(nulls_first=True),
            F("parent__name").asc(nulls_first=True),
            "sort_order",
            "name",
        ]


class BuyersGuideProductCategoryArticlePageRelation(TranslatableMixin, Orderable):
    category = ParentalKey(
        "wagtailpages.BuyersGuideProductCategory",
        related_name="related_article_relations",
    )
    article = models.ForeignKey(
        "wagtailpages.BuyersGuideArticlePage",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )

    panels = [PageChooserPanel("article")]

    def __str__(self):
        return f"{self.category.name} -> {self.article.title}"

    class Meta(TranslatableMixin.Meta, Orderable.Meta):
        pass


class ProductPageVotes(models.Model):
    """
    PNI product voting bins. This does not need translating.
    """

    vote_bins = models.CharField(default="0,0,0,0,0", max_length=50, validators=[int_list_validator])

    def set_votes(self, bin_list):
        """
        There are 5 "bins" for votes: <20%, <40%, <60%, <80%, <100%.
        When setting votes, ensure there are only 5 bins (max)
        """
        bin_list = [str(x) for x in bin_list]
        self.vote_bins = ",".join(bin_list[0:5])
        self.save()

    def get_votes(self):
        """Pull the votes out of the database and split them. Convert to ints."""
        votes = [int(x) for x in self.vote_bins.split(",")]
        return votes

    def get_most_voted(self):
        votes = self.get_votes()
        vote_breakdown = {k: v for (k, v) in enumerate(votes)}
        highest = max(vote_breakdown, key=vote_breakdown.get)
        label = self.get_vote_labels()[highest]

        return {
            "bin": highest,
            "value": votes[highest],
            "label": label[0],
            "localized": label[1],
        }

    def get_vote_labels(self):
        return [
            ("Not creepy", gettext("Not creepy")),
            ("A little creepy", gettext("A little creepy")),
            ("Somewhat creepy", gettext("Somewhat creepy")),
            ("Very creepy", gettext("Very creepy")),
            ("Super creepy", gettext("Super creepy")),
        ]


class ProductPageCategory(TranslatableMixin, Orderable):
    product = ParentalKey(
        "wagtailpages.ProductPage",
        related_name="product_categories",
        on_delete=models.CASCADE,
    )

    category = models.ForeignKey(
        "wagtailpages.BuyersGuideProductCategory",
        related_name="+",
        blank=False,
        null=True,
        on_delete=models.CASCADE,
    )

    panels = [
        SnippetChooserPanel("category"),
    ]

    def __str__(self):
        return self.category.name

    class Meta(TranslatableMixin.Meta):
        verbose_name = "Product Category"


class RelatedProducts(TranslatableMixin, Orderable):
    page = ParentalKey(
        "wagtailpages.ProductPage",
        related_name="related_product_pages",
        on_delete=models.CASCADE,
    )

    related_product = models.ForeignKey(
        "wagtailpages.ProductPage",
        on_delete=models.SET_NULL,
        null=True,
        related_name="+",
    )

    panels = [PageChooserPanel("related_product")]

    class Meta(TranslatableMixin.Meta):
        verbose_name = "Related Product"


class ProductPagePrivacyPolicyLink(TranslatableMixin, Orderable):
    page = ParentalKey(
        "wagtailpages.ProductPage",
        related_name="privacy_policy_links",
        on_delete=models.CASCADE,
    )

    label = models.CharField(max_length=500, help_text="Label for this link on the product page")

    url = models.URLField(max_length=2048, help_text="Privacy policy URL", blank=True)

    panels = [
        FieldPanel("label"),
        FieldPanel("url"),
    ]

    translatable_fields = [
        TranslatableField("label"),
        SynchronizedField("url"),
    ]

    def __str__(self):
        return f"{self.page.title}: {self.label} ({self.url})"

    class Meta(TranslatableMixin.Meta):
        verbose_name = "Privacy Link"


@register_snippet
class Update(TranslatableMixin, index.Indexed, models.Model):
    source = models.URLField(
        max_length=2048,
        help_text="Link to source",
    )

    title = models.CharField(
        max_length=256,
    )

    author = models.CharField(
        max_length=256,
        blank=True,
    )

    featured = models.BooleanField(default=False, help_text="feature this update at the top of the list?")

    snippet = models.TextField(
        max_length=5000,
        blank=True,
    )

    created_date = models.DateField(
        auto_now_add=True,
        help_text="The date this product was created",
    )

    panels = [
        FieldPanel("source"),
        FieldPanel("title"),
        FieldPanel("author"),
        FieldPanel("featured"),
        FieldPanel("snippet"),
    ]

    search_fields = [
        index.SearchField("title", partial_match=True),
        index.FilterField("locale_id"),
    ]

    translatable_fields = [
        SynchronizedField("source"),
        SynchronizedField("title"),
        SynchronizedField("author"),
        SynchronizedField("snippet"),
    ]

    def __str__(self):
        return self.title

    class Meta(TranslatableMixin.Meta):
        verbose_name = "Buyers Guide Product Update"
        verbose_name_plural = "Buyers Guide Product Updates"


class ProductUpdates(TranslatableMixin, Orderable):
    page = ParentalKey(
        "wagtailpages.ProductPage",
        related_name="updates",
        on_delete=models.CASCADE,
    )

    # This is the new update FK to wagtailpages.Update
    update = models.ForeignKey(Update, on_delete=models.SET_NULL, related_name="+", null=True)

    translatable_fields = [
        TranslatableField("update"),
    ]

    panels = [
        SnippetChooserPanel("update"),
    ]

    class Meta(TranslatableMixin.Meta, Orderable.Meta):
        verbose_name = "Product Update"
        ordering = ["sort_order"]


class ProductPage(AirtableMixin, FoundationMetadataPageMixin, Page):
    """
    ProductPage is the superclass that GeneralProductPages inherits from.

    This used to be shared by the SoftwareProductPage, but that page type
    has been removed. In the past, we needed to connect the two page
    types together. This is why this superclass is abstract.

    """

    template = "pages/buyersguide/product_page.html"

    privacy_ding = models.BooleanField(
        verbose_name="*privacy not included ding",
        default=False,
    )
    adult_content = models.BooleanField(
        verbose_name="adult Content",
        default=False,
    )
    uses_wifi = models.BooleanField(
        verbose_name="uses WiFi",
        default=False,
    )
    uses_bluetooth = models.BooleanField(
        verbose_name="uses Bluetooth",
        default=False,
    )
    review_date = models.DateField(
        verbose_name="review Date",
        default=timezone.now,
    )
    company = models.CharField(
        verbose_name="company Name",
        max_length=100,
        blank=True,
    )
    blurb = RichTextField(verbose_name="intro Blurb", features=base_rich_text_options, blank=True)
    product_url = models.URLField(
        verbose_name="product URL",
        max_length=2048,
        blank=True,
    )
    image = models.ForeignKey(
        "wagtailimages.Image",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    worst_case = RichTextField(
        verbose_name="what could happen if something goes wrong?",
        features=base_rich_text_options,
        blank=True,
    )
    tips_to_protect_yourself = RichTextField(features=base_rich_text_options + ["ul"], blank=True)
    mozilla_says = models.BooleanField(
        verbose_name="mozilla Says",
        null=True,
        blank=True,
        help_text="Use 'Yes' for Thumbs Up, 'No' for Thumbs Down, and 'Unknown' for Thumb Sideways",
    )
    time_researched = models.PositiveIntegerField(verbose_name="time spent on research", default=0)

    """
    privacy_policy_links = Orderable, defined in ProductPagePrivacyPolicyLink
    Other "magic" relations that use InlinePanels will follow the same pattern of
    using Wagtail Orderables.
    """

    # What is required to sign up?
    signup_requires_email = ExtendedYesNoField(verbose_name="email")
    signup_requires_phone = ExtendedYesNoField(verbose_name="phone")
    signup_requires_third_party_account = ExtendedYesNoField(verbose_name="third-party account")
    signup_requirement_explanation = models.TextField(
        verbose_name="signup requirement description",
        max_length=5000,
        blank=True,
    )

    # How does it use this data?
    how_does_it_use_data_collected = RichTextField(
        max_length=5000,
        features=base_rich_text_options,
        help_text="How does this product use the data collected?",
        blank=True,
    )
    data_collection_policy_is_bad = models.BooleanField(default=False, verbose_name="mini-ding for bad data use?")

    # Privacy policy
    user_friendly_privacy_policy = ExtendedYesNoField(
        verbose_name="user-friendly privacy information?",
    )

    user_friendly_privacy_policy_helptext = models.TextField(
        verbose_name="user-friendly privacy description", max_length=5000, blank=True
    )

    # Minimum security standards
    show_ding_for_minimum_security_standards = models.BooleanField(
        default=False,
        verbose_name="mini-ding for doesnt meet Minimum Security Standards",
    )
    meets_minimum_security_standards = models.BooleanField(
        verbose_name="does this product meet our Minimum Security Standards?",
        null=True,
        blank=True,
    )
    uses_encryption = ExtendedYesNoField(
        verbose_name="encryption",
    )
    uses_encryption_helptext = models.TextField(verbose_name="description", max_length=5000, blank=True)
    security_updates = ExtendedYesNoField()
    security_updates_helptext = models.TextField(verbose_name="description", max_length=5000, blank=True)
    strong_password = ExtendedYesNoField()
    strong_password_helptext = models.TextField(verbose_name="description", max_length=5000, blank=True)
    manage_vulnerabilities = ExtendedYesNoField(
        verbose_name="manages security vulnerabilities",
    )
    manage_vulnerabilities_helptext = RichTextField(
        max_length=5000,
        features=base_rich_text_options,
        blank=True,
    )
    privacy_policy = ExtendedYesNoField()
    privacy_policy_helptext = models.TextField(  # REPURPOSED: WILL REQUIRE A 'clear' MIGRATION
        verbose_name="description", max_length=5000, blank=True
    )

    # Un-editable voting fields. Don't add these to the content_panels.
    creepiness_value = models.IntegerField(default=0)  # The total points for creepiness
    votes = models.ForeignKey(
        ProductPageVotes,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="votes",
    )

    @classmethod
    def map_import_fields(cls):
        mappings = {
            "Title": "title",
            "Wagtail Page ID": "pk",
            "Slug": "slug",
            "Show privacy ding": "privacy_ding",
            "Has adult content": "adult_content",
            "Uses wifi": "uses_wifi",
            "Uses Bluetooth": "uses_bluetooth",
            "Review date": "review_date",
            "Company": "company",
            "Blurb": "blurb",
            "Product link": "product_url",
            "Worst case": "worst_case",
            "Signup requires email": "signup_requires_email",
            "Signup requires phone number": "signup_requires_phone",
            "Signup requires 3rd party account": "signup_requires_third_party_account",
            "Signup explanation": "signup_requirement_explanation",
            "How it collects data": "how_does_it_use_data_collected",
            "Data collection privacy ding": "data_collection_policy_is_bad",
            "User friendly privacy policy": "user_friendly_privacy_policy",
            "User friendly privacy policy help text": "user_friendly_privacy_policy_helptext",
            "Meets MSS": "meets_minimum_security_standards",
            "Meets MSS privacy policy ding": "show_ding_for_minimum_security_standards",
            "Uses encryption": "uses_encryption",
            "Encryption help text": "uses_encryption_helptext",
            "Has security updates": "security_updates",
            "Security updates help text": "security_updates_helptext",
            "Strong password": "strong_password",
            "Strong password help text": "strong_password_helptext",
            "Manages security vulnerabilities": "manage_vulnerabilities",
            "Manages security help text": "manage_vulnerabilities_helptext",
            "Has privacy policy": "privacy_policy",
            "Privacy policy help text": "privacy_policy_helptext",
            "Mozilla Says": "mozilla_says",
            "Time Researched ": "time_researched",
        }
        return mappings

    def get_export_fields(self):
        """
        This should be a dictionary of the fields to send to Airtable.
        Keys are the Column Names in Airtable. Values are the Wagtail values we want to send.
        """
        return {
            "Title": self.title,
            "Slug": self.slug,
            "Wagtail Page ID": self.pk if hasattr(self, "pk") else 0,
            "Last Updated": str(self.last_published_at) if self.last_published_at else str(timezone.now().isoformat()),
            "Status": self.get_status_for_airtable(),
            "Show privacy ding": self.privacy_ding,
            "Has adult content": self.adult_content,
            "Uses wifi": self.uses_wifi,
            "Uses Bluetooth": self.uses_bluetooth,
            "Review date": str(self.review_date),
            "Company": self.company,
            "Blurb": self.blurb,
            "Product link": self.product_url if self.product_url else "",
            "Worst case": self.worst_case,
            "Signup requires email": self.signup_requires_email,
            "Signup requires phone number": self.signup_requires_phone,
            "Signup requires 3rd party account": self.signup_requires_third_party_account,
            "Signup explanation": self.signup_requirement_explanation,
            "How it collects data": self.how_does_it_use_data_collected,
            "Data collection privacy ding": self.data_collection_policy_is_bad,
            "User friendly privacy policy": self.user_friendly_privacy_policy,
            "User friendly privacy policy help text": self.user_friendly_privacy_policy_helptext,
            "Meets MSS": self.meets_minimum_security_standards,
            "Meets MSS privacy policy ding": self.show_ding_for_minimum_security_standards,
            "Uses encryption": self.uses_encryption,
            "Encryption help text": self.uses_encryption_helptext,
            "Has security updates": self.security_updates,
            "Security updates help text": self.security_updates_helptext,
            "Strong password": self.strong_password,
            "Strong password help text": self.strong_password_helptext,
            "Manages security vulnerabilities": self.manage_vulnerabilities,
            "Manages security help text": self.manage_vulnerabilities_helptext,
            "Has privacy policy": self.privacy_policy,
            "Privacy policy help text": self.privacy_policy_helptext,
            "Mozilla Says": self.mozilla_says,
            "Time Researched": self.time_researched,
            "Tips to protect yourself": self.tips_to_protect_yourself,
        }

    def get_status_for_airtable(self):
        if self.live:
            if self.has_unpublished_changes:
                return "Live + Draft"
            return "Live"
        return "Draft"

    @property
    def original_product(self):
        try:
            original = get_original_by_slug(ProductPage, self.slug)

        except ProductPage.DoesNotExist:
            """
            This may happen when a product was created, got localized,
            then the original product was deleted a new product with the
            same title (and thus, slug) gets created.

            The old localizations are still around, so `sync_locale_trees`
            will see a new page to set up aliases for, but their slug ends
            up conflicting with the slugs for the original localized pages,
            and so they get `-1` appended, meaning we can't find their
            "original" equivalent using their slug: we need to rewrite
            the slug to remove the number suffix first.

            See: https://github.com/wagtail/wagtail/issues/7592

            TODO: Remove this patch code once #7592 is addressed.
            """
            slug = re.sub("(-\\d+)+$", "", self.slug)
            original = get_original_by_slug(ProductPage, slug)

        if original is None:
            return self

        return original

    def get_or_create_votes(self):
        """
        If a page doesn't have a ProductPageVotes objects, create it.
        Regardless of whether or not its created, return the parsed votes.
        """
        if not self.votes:
            votes = ProductPageVotes()
            votes.save()
            self.votes = votes
            self.save()
        return self.votes.get_votes()

    @property
    def total_vote_count(self):
        # Voting only happens on the original product, not "self"
        product = self.original_product
        return sum(product.get_or_create_votes())

    @property
    def creepiness(self):
        # Creepiness is tied to the votes on the original product, not "self"
        product = self.original_product
        try:
            average = product.creepiness_value / product.total_vote_count
        except ZeroDivisionError:
            average = 50
        return average

    @property
    def get_voting_json(self):
        """
        Return a dictionary as a string with the relevant data needed for the frontend:
        """
        product = self.original_product
        votes = product.votes.get_votes()
        data = {
            "creepiness": {
                "vote_breakdown": {k: v for (k, v) in enumerate(votes)},
                "average": product.creepiness,
            },
            "total": product.total_vote_count,
        }
        return json.dumps(data)

    # TODO: refactor meta methods out as part of: https://github.com/mozilla/foundation.mozilla.org/issues/7828
    # See package docs for `get_meta_*` methods: https://pypi.org/project/wagtail-metadata/
    def get_meta_title(self):
        return gettext("*Privacy Not Included review:") + f" {self.title}"

    def get_meta_description(self):
        if self.search_description:
            return self.search_description

        soup = BeautifulSoup(self.blurb, "html.parser")
        first_paragraph = soup.find("p")
        if first_paragraph:
            return first_paragraph.text

        return super().get_meta_description()

    def get_meta_image_url(self, request):
        # Heavy-duty exception handling so the page doesn't crash due to a
        # missing sharing image.
        try:
            return (self.search_image or self.image).get_rendition("original").url
        except Exception:
            return static("_images/buyers-guide/evergreen-social.png")

    content_panels = Page.content_panels + [
        FieldPanel("company"),
        MultiFieldPanel(
            [
                InlinePanel("product_categories", label="Category"),
            ],
            heading="Product Category",
            classname="collapsible",
        ),
        MultiFieldPanel(
            [
                FieldPanel("privacy_ding"),
                FieldPanel("review_date"),
                FieldPanel("adult_content"),
                ImageChooserPanel("image"),
                FieldPanel("product_url"),
                FieldPanel("time_researched"),
                FieldPanel("mozilla_says"),
                FieldPanel("uses_wifi"),
                FieldPanel("uses_bluetooth"),
                FieldPanel("blurb"),
                FieldPanel("worst_case"),
                FieldPanel("tips_to_protect_yourself"),
            ],
            heading="General Product Details",
            classname="collapsible",
        ),
        MultiFieldPanel(
            [
                FieldPanel("signup_requires_email"),
                FieldPanel("signup_requires_phone"),
                FieldPanel("signup_requires_third_party_account"),
                FieldPanel("signup_requirement_explanation"),
            ],
            heading="What can be used to sign up?",
            classname="collapsible",
        ),
        MultiFieldPanel(
            [
                InlinePanel(
                    "privacy_policy_links",
                    label="link",
                    min_num=1,
                    max_num=3,
                ),
            ],
            heading="Privacy policy links",
            classname="collapsible",
        ),
        MultiFieldPanel(
            [
                FieldPanel("meets_minimum_security_standards"),
                FieldPanel("show_ding_for_minimum_security_standards"),
                FieldPanel("uses_encryption"),
                FieldPanel("uses_encryption_helptext"),
                FieldPanel("strong_password"),
                FieldPanel("strong_password_helptext"),
                FieldPanel("security_updates"),
                FieldPanel("security_updates_helptext"),
                FieldPanel("manage_vulnerabilities"),
                FieldPanel("manage_vulnerabilities_helptext"),
                FieldPanel("privacy_policy"),
                FieldPanel("privacy_policy_helptext"),
            ],
            heading="Security",
            classname="collapsible",
        ),
        MultiFieldPanel(
            [InlinePanel("updates", label="Update")],
            heading="News Links",
            classname="collapsible",
        ),
        MultiFieldPanel(
            [InlinePanel("related_product_pages", label="Product")],
            heading="Related Products",
        ),
        MultiFieldPanel(
            [
                InlinePanel(
                    "related_article_relations",
                    heading="Related articles",
                    label="Article",
                    max_num=5,
                ),
            ],
            heading="Related Articles",
        ),
    ]

    translatable_fields = [
        # Promote tab fields
        SynchronizedField("slug"),
        TranslatableField("seo_title"),
        SynchronizedField("show_in_menus"),
        TranslatableField("search_description"),
        SynchronizedField("search_image"),
        # Content tab fields
        TranslatableField("title"),
        SynchronizedField("privacy_ding"),
        SynchronizedField("adult_content"),
        SynchronizedField("uses_wifi"),
        SynchronizedField("uses_bluetooth"),
        SynchronizedField("review_date"),
        SynchronizedField("company"),
        TranslatableField("blurb"),
        SynchronizedField("product_url"),
        SynchronizedField("image"),
        TranslatableField("worst_case"),
        SynchronizedField("product_categories"),
        SynchronizedField("signup_requires_email"),
        SynchronizedField("signup_requires_phone"),
        SynchronizedField("signup_requires_third_party_account"),
        TranslatableField("signup_requirement_explanation"),
        SynchronizedField("signup_requires_third_party_account"),
        TranslatableField("how_does_it_use_data_collected"),
        SynchronizedField("data_collection_policy_is_bad"),
        SynchronizedField("user_friendly_privacy_policy"),
        TranslatableField("user_friendly_privacy_policy_helptext"),
        SynchronizedField("privacy_policy_links"),
        SynchronizedField("show_ding_for_minimum_security_standards"),
        SynchronizedField("meets_minimum_security_standards"),
        SynchronizedField("uses_encryption"),
        TranslatableField("uses_encryption_helptext"),
        SynchronizedField("security_updates"),
        TranslatableField("security_updates_helptext"),
        SynchronizedField("strong_password"),
        TranslatableField("strong_password_helptext"),
        SynchronizedField("manage_vulnerabilities"),
        TranslatableField("manage_vulnerabilities_helptext"),
        SynchronizedField("privacy_policy"),
        TranslatableField("privacy_policy_helptext"),
        # non-translatable fields:
        SynchronizedField("mozilla_says"),
        SynchronizedField("related_product_pages"),
        SynchronizedField("time_researched"),
        SynchronizedField("updates"),
        TranslatableField("tips_to_protect_yourself"),
    ]

    @property
    def product_type(self):
        return "unknown"

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["product"] = self
        language_code = get_language_from_request(request)
        context["categories"] = get_categories_for_locale(language_code)
        context["featured_cta"] = self.get_featured_cta()
        context["mediaUrl"] = settings.MEDIA_URL
        context["use_commento"] = settings.USE_COMMENTO
        context["pageTitle"] = f"{self.title} | " + gettext("Privacy & security guide") + " | Mozilla Foundation"
        return context

    def get_related_articles(self) -> models.QuerySet["BuyersGuideArticlePage"]:
        return orderables.get_related_items(
            self.related_article_relations.all(),
            "article",
        )

    def get_primary_related_articles(self) -> models.QuerySet["BuyersGuideArticlePage"]:
        return self.get_related_articles()[:3]

    def get_secondary_related_articles(
        self,
    ) -> models.QuerySet["BuyersGuideArticlePage"]:
        return self.get_related_articles()[3:]

    def get_featured_cta(self):
        if ProductPageCategory.objects.filter(product=self, category__show_cta=True).exists():
            return get_buyersguide_featured_cta(self)
        else:
            return None

    def serve(self, request, *args, **kwargs):
        # In Wagtail we use the serve() method to detect POST submissions.
        # Alternatively, this could be a routable view.
        # For more on this, see the docs here:
        # https://docs.wagtail.io/en/stable/reference/pages/model_recipes.html#overriding-the-serve-method
        if request.body and request.method == "POST":
            # If the request is POST. Parse the body.
            data = json.loads(request.body)
            # If the POST body has a productID and value, it's someone voting on the product
            if data.get("value"):
                # Product ID and Value can both be zero. It's impossible to get a Page with ID of zero.
                try:
                    value = int(data["value"])
                except ValueError:
                    return HttpResponseNotAllowed("Product ID or value is invalid")

                if value < 0 or value > 100:
                    return HttpResponseNotAllowed("Cannot save vote")

                try:
                    # Get the english version of this product, as votes should only be recorded
                    # for the "authoritative" product instance, not specific locale versions.
                    product = self.original_product

                    # 404 if the product exists but isn't live and the user isn't logged in.
                    if (not product.live and not request.user.is_authenticated) or not product:
                        return HttpResponseNotFound("Product does not exist")

                    # Save the new voting totals
                    product.creepiness_value = product.creepiness_value + value

                    # Add the vote to the vote bin
                    if not product.votes:
                        # If there is no vote bin attached to this product yet, create one now.
                        votes = ProductPageVotes()
                        votes.save()
                        product.votes = votes

                    # Add the vote to the proper "vote bin"
                    votes = product.votes.get_votes()
                    index = int((value - 1) / 20)
                    votes[index] += 1
                    product.votes.set_votes(votes)

                    # Don't save this as a revision with .save_revision() as to not spam the Audit log
                    # And don't make this live with .publish(). The Page model will have the proper
                    # data stored on it already, and the revision history won't be spammed by votes.
                    product.save()
                    return HttpResponse("Vote recorded", content_type="text/plain")
                except ProductPage.DoesNotExist:
                    return HttpResponseNotFound("Missing page")
                except ValidationError as ex:
                    return HttpResponseNotAllowed(f"Payload validation failed: {ex}")
                except Error as ex:
                    print(f"Internal Server Error (500) for ProductPage: {ex.message} ({type(ex)})")
                    return HttpResponseServerError()

        self.get_or_create_votes()

        return super().serve(request, *args, **kwargs)

    def save(self, *args, **kwargs):
        # When a new ProductPage is created, ensure a vote bin always exists.
        # We can use save() or a post-save Wagtail hook.
        save = super().save(*args, **kwargs)
        self.get_or_create_votes()
        return save

    class Meta:
        verbose_name = "Product Page"


class BuyersGuideProductPageArticlePageRelation(TranslatableMixin, Orderable):
    product = ParentalKey(
        "wagtailpages.ProductPage",
        related_name="related_article_relations",
    )
    article = models.ForeignKey(
        "wagtailpages.BuyersGuideArticlePage",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )

    panels = [PageChooserPanel("article")]

    def __str__(self):
        return f"{self.product.name} -> {self.article.title}"

    class Meta(TranslatableMixin.Meta, Orderable.Meta):
        pass


class GeneralProductPage(ProductPage):
    template = "pages/buyersguide/product_page.html"

    camera_device = ExtendedYesNoField(
        verbose_name="camera: Device",
    )

    camera_app = ExtendedYesNoField(
        verbose_name="camera: App",
    )

    microphone_device = ExtendedYesNoField(
        verbose_name="microphone: Device",
    )

    microphone_app = ExtendedYesNoField(
        verbose_name="microphone: App",
    )

    location_device = ExtendedYesNoField(
        verbose_name="tracks location: Device",
    )

    location_app = ExtendedYesNoField(
        verbose_name="tracks location: App",
    )

    # What data does it collect?

    personal_data_collected = models.TextField(
        verbose_name="personal",
        max_length=5000,
        blank=True,
    )

    biometric_data_collected = models.TextField(
        verbose_name="body Related",
        max_length=5000,
        blank=True,
    )

    social_data_collected = models.TextField(
        verbose_name="social",
        max_length=5000,
        blank=True,
    )

    # How can you control your data

    how_can_you_control_your_data = RichTextField(
        max_length=5000,
        features=base_rich_text_options,
        help_text="How does this product let you control your data?",
        blank=True,
    )

    data_control_policy_is_bad = models.BooleanField(default=False, verbose_name="mini-ding for bad data control?")

    # Company track record

    company_track_record = models.CharField(
        verbose_name="company's known track record?",
        choices=TRACK_RECORD_CHOICES,
        default="Average",
        max_length=20,
    )

    track_record_is_bad = models.BooleanField(default=False, verbose_name="mini-ding for bad track record")

    track_record_details = RichTextField(
        max_length=5000,
        features=base_rich_text_options,
        help_text="Describe the track record of this company here.",
        blank=True,
    )

    # Child Safety Blurb

    child_safety_blurb = RichTextField(
        max_length=5000,
        features=base_rich_text_options,
        help_text="Child safety information, if applicable.",
        blank=True,
    )

    # Offline use

    offline_capable = ExtendedYesNoField(
        verbose_name="can this product be used offline?",
    )

    offline_use_description = RichTextField(
        max_length=5000,
        features=base_rich_text_options,
        help_text="Describe how this product can be used offline.",
        blank=True,
    )

    # Artificial Intelligence

    uses_ai = ExtendedYesNoField(
        verbose_name="does the product use AI?",
    )
    ai_helptext = RichTextField(
        max_length=5000,
        features=base_rich_text_options,
        help_text="Helpful text around AI to show on the product page",
        blank=True,
    )
    ai_is_untrustworthy = ExtendedYesNoField(
        verbose_name="is this AI untrustworthy?",
    )
    ai_is_untrustworthy_ding = models.BooleanField(
        verbose_name="mini-ding for bad AI",
        default=False,
    )
    ai_what_can_it_do = RichTextField(
        verbose_name="what kind of decisions does the AI make about you or for you?",
        blank=True,
    )
    ai_is_transparent = ExtendedYesNoField(
        verbose_name="is the company transparent about how the AI works?",
    )
    ai_is_transparent_helptext = models.TextField(
        verbose_name="aI transparency description",
        max_length=5000,
        blank=True,
    )
    ai_can_user_control = ExtendedYesNoField(
        verbose_name="does the user have control over the AI features?",
    )
    ai_can_user_control_helptext = models.TextField(
        verbose_name="control of AI description",
        max_length=5000,
        blank=True,
    )

    @classmethod
    def map_import_fields(cls):
        generic_product_import_fields = super().map_import_fields()
        general_product_mappings = {
            "Has camera device": "camera_device",
            "Has camera app": "camera_app",
            "Has microphone device": "microphone_device",
            "Has microphone app": "microphone_app",
            "Has location device": "location_device",
            "Has location app": "location_app",
            "Personal data collected": "personal_data_collected",
            "Biometric data collected": "biometric_data_collected",
            "Social data collected": "social_data_collected",
            "How you can control your data": "how_can_you_control_your_data",
            "Company track record": "company_track_record",
            "Show company track record privacy ding": "track_record_is_bad",
            "Child safety blurb": "child_safety_blurb",
            "Offline capable": "offline_capable",
            "Offline use": "offline_use_description",
            "Uses AI": "uses_ai",
            "AI help text": "ai_helptext",
            "AI is transparent": "ai_is_transparent",
            "AI is transparent help text": "ai_is_transparent_helptext",
            "AI is untrustworthy": "ai_is_untrustworthy",
            "AI is untrustworthy ding": "ai_is_untrustworthy_ding",
            "AI What can it do": "ai_what_can_it_do",
            "AI can user control": "ai_can_user_control",
            "AI can user control help text": "ai_can_user_control_helptext",
        }
        # Return the merged fields
        return {**generic_product_import_fields, **general_product_mappings}

    def get_export_fields(self):
        """
        This should be a dictionary of the fields to send to Airtable.
        Keys are the Column Names in Airtable. Values are the Wagtail values we want to send.
        """
        generic_product_data = super().get_export_fields()
        general_product_data = {
            "Has camera device": self.camera_device,
            "Has camera app": self.camera_app,
            "Has microphone device": self.microphone_device,
            "Has microphone app": self.microphone_app,
            "Has location device": self.location_device,
            "Has location app": self.location_app,
            "Personal data collected": self.personal_data_collected,
            "Biometric data collected": self.biometric_data_collected,
            "Social data collected": self.social_data_collected,
            "How you can control your data": self.how_can_you_control_your_data,
            "Company track record": self.company_track_record,
            "Show company track record privacy ding": self.track_record_is_bad,
            "Child safety blurb": self.child_safety_blurb,
            "Offline capable": self.offline_capable,
            "Offline use": self.offline_use_description,
            "Uses AI": self.uses_ai,
            "AI is transparent": self.ai_is_transparent,
            "AI is transparent help text": self.ai_is_transparent_helptext,
            "AI help text": self.ai_helptext,
            "AI is untrustworthy": self.ai_is_untrustworthy,
            "AI is untrustworthy ding": self.ai_is_untrustworthy_ding,
            "AI What can it do": self.ai_what_can_it_do,
            "AI can user control": self.ai_can_user_control,
            "AI can user control help text": self.ai_can_user_control_helptext,
        }
        # Merge the two dicts together.
        data = {**generic_product_data, **general_product_data}
        return data

    # administrative panels
    content_panels = ProductPage.content_panels.copy()
    content_panels = insert_panels_after(
        content_panels,
        "General Product Details",
        [
            MultiFieldPanel(
                [
                    FieldPanel("camera_device"),
                    FieldPanel("camera_app"),
                    FieldPanel("microphone_device"),
                    FieldPanel("microphone_app"),
                    FieldPanel("location_device"),
                    FieldPanel("location_app"),
                ],
                heading="Can it snoop on me?",
                classname="collapsible",
            ),
        ],
    )

    content_panels = insert_panels_after(
        content_panels,
        "What can be used to sign up?",
        [
            MultiFieldPanel(
                [
                    FieldPanel("personal_data_collected"),
                    FieldPanel("biometric_data_collected"),
                    FieldPanel("social_data_collected"),
                    FieldPanel("how_does_it_use_data_collected"),
                    FieldPanel("data_collection_policy_is_bad"),
                    FieldPanel("how_can_you_control_your_data"),
                    FieldPanel("data_control_policy_is_bad"),
                    FieldPanel("company_track_record"),
                    FieldPanel("track_record_details"),
                    FieldPanel("track_record_is_bad"),
                    FieldPanel("child_safety_blurb"),
                    FieldPanel("offline_capable"),
                    FieldPanel("offline_use_description"),
                    FieldPanel("user_friendly_privacy_policy"),
                    FieldPanel("user_friendly_privacy_policy_helptext"),
                ],
                heading="What data does the company collect?",
                classname="collapsible",
            ),
        ],
    )

    content_panels = insert_panels_after(
        content_panels,
        "Security",
        [
            MultiFieldPanel(
                [
                    FieldPanel("uses_ai"),
                    FieldPanel("ai_helptext"),
                    FieldPanel("ai_is_untrustworthy"),
                    FieldPanel("ai_is_untrustworthy_ding"),
                    FieldPanel("ai_what_can_it_do"),
                    FieldPanel("ai_is_transparent"),
                    FieldPanel("ai_is_transparent_helptext"),
                    FieldPanel("ai_can_user_control"),
                    FieldPanel("ai_can_user_control_helptext"),
                ],
                heading="Artificial Intelligence",
                classname="collapsible",
            ),
        ],
    )

    translatable_fields = ProductPage.translatable_fields + [
        TranslatableField("personal_data_collected"),
        TranslatableField("biometric_data_collected"),
        TranslatableField("social_data_collected"),
        TranslatableField("how_can_you_control_your_data"),
        SynchronizedField("data_control_policy_is_bad"),
        SynchronizedField("company_track_record"),
        SynchronizedField("track_record_is_bad"),
        TranslatableField("track_record_details"),
        TranslatableField("child_safety_blurb"),
        SynchronizedField("offline_capable"),
        TranslatableField("offline_use_description"),
        SynchronizedField("uses_ai"),
        SynchronizedField("ai_is_transparent"),
        TranslatableField("ai_is_transparent_helptext"),
        TranslatableField("ai_helptext"),
        SynchronizedField("ai_is_untrustworthy"),
        SynchronizedField("ai_is_untrustworthy_ding"),
        TranslatableField("ai_what_can_it_do"),
        SynchronizedField("ai_can_user_control"),
        TranslatableField("ai_can_user_control_helptext"),
    ]

    @property
    def product_type(self):
        return "general"

    class Meta:
        verbose_name = "General Product Page"


class ExcludedCategories(TranslatableMixin, Orderable):
    """
    This allows us to filter categories from showing up on the PNI site
    """

    page = ParentalKey("wagtailpages.BuyersGuidePage", related_name="excluded_categories")
    category = models.ForeignKey(
        BuyersGuideProductCategory,
        on_delete=models.CASCADE,
    )

    panels = [
        SnippetChooserPanel("category"),
    ]

    def __str__(self):
        return self.category.name

    class Meta(TranslatableMixin.Meta):
        verbose_name = "Excluded Category"

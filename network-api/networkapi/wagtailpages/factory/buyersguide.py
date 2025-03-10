# TODO: Move these factories to the wagtailpages app.
# To avoid too many code conflicts, this should happen after PR 6433 is merged
from datetime import date, datetime, timedelta, timezone
from random import choice, randint, random, randrange, shuffle

from factory import Faker, LazyFunction, SubFactory, post_generation
from factory.django import DjangoModelFactory
from wagtail.images.models import Image
from wagtail_factories import PageFactory

from networkapi.utility.faker import ImageProvider, generate_fake_data
from networkapi.utility.faker.helpers import get_random_objects, reseed
from networkapi.wagtailpages import models as pagemodels
from networkapi.wagtailpages.factory import profiles as profile_factories
from networkapi.wagtailpages.factory.donation import DonationModalFactory
from networkapi.wagtailpages.factory.image_factory import ImageFactory
from networkapi.wagtailpages.factory.petition import PetitionFactory

Faker.add_provider(ImageProvider)


def get_random_option(options=[]):
    return choice(options)


def get_extended_boolean_value():
    return get_random_option(["Yes", "No", "U"])


def get_extended_yes_no_value():
    return get_random_option(["Yes", "No", "NA", "CD"])


def get_lowest_content_page_category():
    return sorted(
        [(cat.published_product_page_count, cat) for cat in pagemodels.BuyersGuideProductCategory.objects.all()],
        key=lambda t: t[0],
    )[0][1]


class BuyersGuideProductCategoryArticlePageRelationFactory(DjangoModelFactory):
    class Meta:
        model = pagemodels.BuyersGuideProductCategoryArticlePageRelation


class BuyersGuideProductPageArticlePageRelationFactory(DjangoModelFactory):
    class Meta:
        model = pagemodels.BuyersGuideProductPageArticlePageRelation


class BuyersGuideEditorialContentIndexPageArticlePageRelationFactory(DjangoModelFactory):
    class Meta:
        model = pagemodels.BuyersGuideEditorialContentIndexPageArticlePageRelation


class BuyersGuideCallToActionFactory(DjangoModelFactory):
    class Meta:
        model = pagemodels.BuyersGuideCallToAction

    title = Faker("sentence", nb_words=7, variable_nb_words=True)
    content = Faker("paragraph", nb_sentences=3, variable_nb_sentences=True)
    link_label = Faker("sentence", nb_words=2)
    link_target_url = Faker("url")


class ProductUpdateFactory(DjangoModelFactory):
    class Meta:
        model = pagemodels.Update

    source = Faker("url")
    title = Faker("sentence")
    author = Faker("sentence")
    featured = Faker("boolean")
    snippet = Faker("sentence")


class BuyersGuidePageFactory(PageFactory):
    class Meta:
        model = pagemodels.BuyersGuidePage

    call_to_action = SubFactory(BuyersGuideCallToActionFactory)


class BuyersGuidePageHeroSupportingArticleRelationFactory(DjangoModelFactory):
    class Meta:
        model = pagemodels.BuyersGuidePageHeroSupportingArticleRelation

    page = SubFactory(BuyersGuidePageFactory)
    article = SubFactory(
        "networkapi.wagtailpages.factory.buyersguide.BuyersGuideArticlePageFactory",
    )


class BuyersGuidePageFeaturedArticleRelationFactory(DjangoModelFactory):
    class Meta:
        model = pagemodels.BuyersGuidePageFeaturedArticleRelation

    page = SubFactory(BuyersGuidePageFactory)
    article = SubFactory(
        "networkapi.wagtailpages.factory.buyersguide.BuyersGuideArticlePageFactory",
    )


class BuyersGuidePageFeaturedUpdateRelationFactory(DjangoModelFactory):
    class Meta:
        model = pagemodels.BuyersGuidePageFeaturedUpdateRelation

    page = SubFactory(BuyersGuidePageFactory)
    update = SubFactory(
        "networkapi.wagtailpages.factory.buyersguide.ProductUpdateFactory",
    )


class ProductPageVotesFactory(DjangoModelFactory):
    class Meta:
        model = pagemodels.ProductPageVotes

    vote_bins = LazyFunction(lambda: ",".join([str(randint(1, 50)) for x in range(0, 5)]))


class ProductPageFactory(PageFactory):
    class Meta:
        model = pagemodels.ProductPage

    title = Faker("sentence")

    privacy_ding = Faker("boolean")
    adult_content = Faker("boolean")
    uses_wifi = Faker("boolean")
    uses_bluetooth = Faker("boolean")
    company = Faker("company")
    blurb = Faker("sentence")
    product_url = Faker("url")
    worst_case = Faker("sentence")
    first_published_at = Faker("past_datetime", start_date="-2d", tzinfo=timezone.utc)
    last_published_at = Faker("past_datetime", start_date="-1d", tzinfo=timezone.utc)

    @post_generation
    def assign_random_categories(self, create, extracted, **kwargs):
        # late import to prevent circular dependency
        from networkapi.wagtailpages.models import ProductPageCategory

        ceiling = 1.0
        while True:
            odds = random()
            if odds < ceiling:
                category = get_lowest_content_page_category()
                ProductPageCategory.objects.get_or_create(product=self, category=category)
                if category.parent:
                    ProductPageCategory.objects.get_or_create(product=self, category=category.parent)
                ceiling = ceiling / 5
            else:
                return

    @post_generation
    def set_random_review_date(self, create, extracted, **kwargs):
        if "Percy" not in self.title:
            start_date = date(2020, 10, 1)
            end_date = date(2021, 1, 30)
            time_between_dates = end_date - start_date
            days_between_dates = time_between_dates.days
            random_number_of_days = randrange(days_between_dates)
            self.review_date = start_date + timedelta(days=random_number_of_days)

    @post_generation
    def set_random_creepiness(self, create, extracted, **kwargs):
        self.get_or_create_votes()
        single_vote = [0, 0, 1, 0, 0]
        shuffle(single_vote)
        self.votes.set_votes(single_vote)
        self.creepiness_value = randint(0, 100)


class GeneralProductPageFactory(ProductPageFactory):
    class Meta:
        model = pagemodels.GeneralProductPage

    camera_app = LazyFunction(get_extended_yes_no_value)
    camera_device = LazyFunction(get_extended_yes_no_value)
    microphone_app = LazyFunction(get_extended_yes_no_value)
    microphone_device = LazyFunction(get_extended_yes_no_value)
    location_app = LazyFunction(get_extended_yes_no_value)
    location_device = LazyFunction(get_extended_yes_no_value)
    personal_data_collected = Faker("sentence")
    biometric_data_collected = Faker("sentence")
    social_data_collected = Faker("sentence")
    how_can_you_control_your_data = Faker("sentence")
    data_control_policy_is_bad = Faker("boolean")
    company_track_record = get_random_option(["Great", "Average", "Needs Improvement", "Bad"])
    track_record_is_bad = Faker("boolean")
    track_record_details = Faker("sentence")
    offline_capable = LazyFunction(get_extended_yes_no_value)
    offline_use_description = Faker("sentence")
    uses_ai = LazyFunction(get_extended_yes_no_value)
    ai_is_transparent = LazyFunction(get_extended_yes_no_value)
    ai_helptext = Faker("sentence")


class ProductPagePrivacyPolicyLinkFactory(DjangoModelFactory):
    class Meta:
        model = pagemodels.ProductPagePrivacyPolicyLink

    label = Faker("sentence")
    url = Faker("url")


class BuyersGuideEditorialContentIndexPageFactory(PageFactory):
    class Meta:
        model = pagemodels.BuyersGuideEditorialContentIndexPage

    title = "Articles"


class BuyersGuideArticlePageFactory(PageFactory):
    class Meta:
        model = pagemodels.BuyersGuideArticlePage

    title = Faker("sentence")
    hero_image = SubFactory(ImageFactory)
    first_published_at = Faker("past_datetime", start_date="-30d", tzinfo=timezone.utc)
    search_image = SubFactory(ImageFactory)
    search_description = Faker("paragraph", nb_sentences=5, variable_nb_sentences=True)
    body = Faker(
        provider="streamfield",
        fields=(
            "paragraph",
            "image",
            "image_text",
            "image_text_mini",
            "video",
            "linkbutton",
            "spacer",
            "quote",
        ),
    )


class BuyersGuideCampaignPageFactory(PageFactory):
    class Meta:
        model = pagemodels.BuyersGuideCampaignPage

    header = Faker("sentence")
    title = Faker("sentence")
    cta = SubFactory(PetitionFactory)
    narrowed_page_content = Faker("boolean", chance_of_getting_true=50)
    body = Faker(
        provider="streamfield",
        fields=(
            "header",
            "paragraph",
            "image",
            "spacer",
            "image_text",
            "quote",
        ),
    )


class BuyersGuideContentCategoryFactory(DjangoModelFactory):
    class Meta:
        model = pagemodels.BuyersGuideContentCategory

    title = Faker("word")


class BuyersGuideArticlePageAuthorProfileRelationFactory(DjangoModelFactory):
    class Meta:
        model = pagemodels.BuyersGuideArticlePageAuthorProfileRelation

    page = SubFactory(BuyersGuideArticlePageFactory)
    author_profile = SubFactory(profile_factories.ProfileFactory)


class BuyersGuideArticlePageContentCategoryRelationFactory(DjangoModelFactory):
    class Meta:
        model = pagemodels.BuyersGuideArticlePageContentCategoryRelation

    page = SubFactory(BuyersGuideArticlePageFactory)
    content_category = SubFactory(BuyersGuideContentCategoryFactory)


class BuyersGuideArticlePageRelatedArticleRelationFactory(DjangoModelFactory):
    class Meta:
        model = pagemodels.BuyersGuideArticlePageRelatedArticleRelation

    page = SubFactory(BuyersGuideArticlePageFactory)
    article = SubFactory(BuyersGuideArticlePageFactory)


class BuyersGuideCampaignPageDonationModalRelationFactory(DjangoModelFactory):
    class Meta:
        model = pagemodels.BuyersGuideCampaignPageDonationModalRelation

    page = SubFactory(BuyersGuideCampaignPageFactory)
    donation_modal = SubFactory(DonationModalFactory)


def create_general_product_visual_regression_product(seed, pni_homepage):
    # There are no random fields here: *everything* is prespecified
    GeneralProductPageFactory.create(
        # page fields
        title="General Percy Product",
        first_published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        last_published_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        parent=pni_homepage,
        # product fields
        privacy_ding=True,
        adult_content=True,
        uses_wifi=True,
        uses_bluetooth=True,
        review_date=date(2025, 1, 1),
        company="Percy Corp",
        blurb="This is a general product specifically created for visual regression testing",
        product_url="http://example.com/general-percy",
        worst_case="Visual regression fails",
        # general product fields
        camera_app="Yes",
        camera_device="No",
        microphone_app="NA",
        microphone_device="CD",
        location_app="Yes",
        location_device="No",
        personal_data_collected="Is personal data getting collected?",
        biometric_data_collected="Is biometric data getting collected?",
        social_data_collected="Is social data getting collected?",
        how_can_you_control_your_data="So, how can you control your data?",
        data_control_policy_is_bad=True,
        company_track_record="Needs Improvement",
        track_record_is_bad=True,
        track_record_details="<p> What kind of track record are we talking about? </p>",
        offline_capable="Yes",
        offline_use_description="<p> Although it is unclear how offline capabilities work </p>",
        uses_ai="NA",
        ai_is_transparent="No",
        ai_helptext="The AI is a black box and no one knows how it works",
    )


def generate(seed):
    reseed(seed)

    print("Generating PNI Homepage")
    pni_homepage = BuyersGuidePageFactory.create(
        parent=pagemodels.Homepage.objects.first(),
        title="* Privacy not included",
        slug="privacynotincluded",
    )

    print("Generating visual regression test products")
    create_general_product_visual_regression_product(seed, pni_homepage)

    print("Generating 52 ProductPages")
    for i in range(52):
        # General products
        general_page = GeneralProductPageFactory.create(
            parent=pni_homepage,
        )
        general_page.save_revision().publish()

    print("Crosslinking related products")
    product_pages = pagemodels.ProductPage.objects.all()
    total_product_pages = product_pages.count()
    for product_page in product_pages:
        # Create a new orderable 3 times.
        # Each page will be randomly selected from an existing factory page.
        for i in range(3):
            random_number = randint(1, total_product_pages) - 1
            random_page = product_pages[random_number]
            related_product = pagemodels.RelatedProducts(
                page=product_page,
                related_product=random_page,
            )
            related_product.save()
            product_page.related_product_pages.add(related_product)

            # Create new ProductUpdates orderable for each PNI product
            product_update = pagemodels.ProductUpdates(page=product_page, update=ProductUpdateFactory())
            product_update.save()
            product_page.updates.add(product_update)

            # Create three new privacy policy links for each PNI product
            privacy_orderable = ProductPagePrivacyPolicyLinkFactory(
                page=product_page,
            )
            privacy_orderable.save()
            product_page.privacy_policy_links.add(privacy_orderable)

    reseed(seed)

    print("Generating Buyer's Guide product updates")
    generate_fake_data(ProductUpdateFactory, 15)

    reseed(seed)

    print("Generating predictable PNI images")
    pni_images = Image.objects.filter(collection__name="pni products")
    for product_page in pagemodels.ProductPage.objects.all():
        if pni_images:
            product_page.image = choice(pni_images)
        else:
            product_page.image = ImageFactory()
        product_page.save()
    # TODO: link updates into products

    print("Generating buyers guide editorial content")
    editorial_content_index = BuyersGuideEditorialContentIndexPageFactory(parent=pni_homepage)
    for _ in range(3):
        BuyersGuideContentCategoryFactory()
    articles = []
    for _ in range(12):
        article = BuyersGuideArticlePageFactory(parent=editorial_content_index)
        for profile in get_random_objects(pagemodels.Profile, max_count=3):
            BuyersGuideArticlePageAuthorProfileRelationFactory(
                page=article,
                author_profile=profile,
            )
        if article.id % 2 == 0:
            # Articles with even id get the content category
            for category in get_random_objects(pagemodels.BuyersGuideContentCategory, max_count=2):
                BuyersGuideArticlePageContentCategoryRelationFactory(
                    page=article,
                    content_category=category,
                )
        # Add all previously existing articles as related articles
        for existing_article in articles:
            BuyersGuideArticlePageRelatedArticleRelationFactory(
                page=article,
                article=existing_article,
            )
        articles.append(article)

    # Creating Buyersguide Campaign pages and accompanying donation modals
    for _ in range(5):
        campaign_page = BuyersGuideCampaignPageFactory(parent=editorial_content_index)
        BuyersGuideCampaignPageDonationModalRelationFactory(page=campaign_page)

    # Buyerguide homepage hero article
    pni_homepage.hero_featured_article = pagemodels.BuyersGuideArticlePage.objects.first()
    pni_homepage.full_clean()
    pni_homepage.save()
    # Buyerguide homepage hero supporting articles
    supporting_articles = get_random_objects(pagemodels.BuyersGuideArticlePage, exact_count=3)
    for index, article in enumerate(supporting_articles):
        BuyersGuidePageHeroSupportingArticleRelationFactory(
            page=pni_homepage,
            article=article,
            sort_order=index,
        )
    # Buyerguide homepage featured advice article
    pni_homepage.featured_advice_article = pagemodels.BuyersGuideArticlePage.objects.last()
    pni_homepage.full_clean()
    pni_homepage.save()
    # Buyersguide homepage featured articles
    featured_articles = get_random_objects(
        source=pagemodels.BuyersGuideArticlePage.objects.exclude(id__in=supporting_articles),
        exact_count=3,
    )
    for index, article in enumerate(featured_articles):
        BuyersGuidePageFeaturedArticleRelationFactory(
            page=pni_homepage,
            article=article,
            sort_order=index,
        )
    # Buyersguide homepage featured product updates
    for index, update in enumerate(get_random_objects(pagemodels.Update, exact_count=3)):
        BuyersGuidePageFeaturedUpdateRelationFactory(
            page=pni_homepage,
            update=update,
            sort_order=index,
        )

    # Adding related articles to the Editorial Content Index Page
    for index, article in enumerate(get_random_objects(pagemodels.BuyersGuideArticlePage, exact_count=3)):
        BuyersGuideEditorialContentIndexPageArticlePageRelationFactory(
            page=editorial_content_index,
            article=article,
            sort_order=index,
        )

    # Adding related articles to Product Pages
    for product in pagemodels.ProductPage.objects.all():
        for index, article in enumerate(get_random_objects(pagemodels.BuyersGuideArticlePage, exact_count=5)):
            BuyersGuideProductPageArticlePageRelationFactory(
                product=product,
                article=article,
                sort_order=index,
            )

    # Adding related articles to Categories
    for product_category in pagemodels.BuyersGuideProductCategory.objects.all():
        for index, article in enumerate(get_random_objects(pagemodels.BuyersGuideArticlePage, max_count=6)):
            BuyersGuideProductCategoryArticlePageRelationFactory(
                category=product_category,
                article=article,
                sort_order=index,
            )

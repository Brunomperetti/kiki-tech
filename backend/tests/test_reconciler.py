from app.catalog.models import ChannelListing,MatchMethod,Product,ReconciliationStatus
from app.catalog.reconciler import CatalogReconciler
def product(**kw): return Product(sku="A1",ean="7791234567890",name="Café premium 500g",brand="Kiki",price=10,stock=2,**kw)
def test_match_by_sku():
 r=CatalogReconciler().reconcile([product()],[ChannelListing(external_id="ML1",sku="A1",title="Otro")])[0]; assert (r.status,r.match_method)==(ReconciliationStatus.ALREADY_PUBLISHED,MatchMethod.SKU)
def test_match_by_ean():
 r=CatalogReconciler().reconcile([product()],[ChannelListing(external_id="ML1",sku="X",ean="7791234567890")])[0]; assert r.match_method==MatchMethod.EAN
def test_no_match_is_candidate(): assert CatalogReconciler().reconcile([product()],[])[0].status==ReconciliationStatus.CANDIDATE_TO_PUBLISH
def test_text_match_requires_review():
 r=CatalogReconciler().reconcile([product()],[ChannelListing(external_id="ML1",title="Cafe premium 500g")])[0]; assert r.status==ReconciliationStatus.REVIEW_REQUIRED
def test_multiple_sku_matches_are_duplicate():
 listings=[ChannelListing(external_id=str(i),sku="A1") for i in range(2)]; assert CatalogReconciler().reconcile([product()],listings)[0].status==ReconciliationStatus.POSSIBLE_DUPLICATE
def test_duplicate_product_sku():
 results=CatalogReconciler().reconcile([product(),product()],[]); assert all(x.status==ReconciliationStatus.POSSIBLE_DUPLICATE for x in results)
def test_incomplete_data():
 p=Product(sku="A1",ean="7791234567890",name=None,price=None,stock=1); assert CatalogReconciler().reconcile([p],[])[0].status==ReconciliationStatus.INCOMPLETE_DATA
def test_unmatched_listing_is_reported():
 result=CatalogReconciler().reconcile([], [ChannelListing(external_id="ML1")])[0]; assert result.status==ReconciliationStatus.UNMATCHED_ML_LISTING

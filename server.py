"""Python Flask WebApp Auth0 integration example
"""
from functools import wraps
from os import environ as env
from werkzeug.exceptions import HTTPException
from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker
from db_setup import Base, CatalogItem, Category, User
from dotenv import load_dotenv, find_dotenv
from flask import Flask
from flask import jsonify
from flask import redirect
from flask import render_template
from flask import session as login_session
from flask import url_for
from flask import make_response
from flask import request
from flask import flash
from authlib.flask.client import OAuth
from six.moves.urllib.parse import urlencode
import requests
import json


import constants

ENV_FILE = find_dotenv()
if ENV_FILE:
    load_dotenv(ENV_FILE)

AUTH0_CALLBACK_URL = env.get(constants.AUTH0_CALLBACK_URL)
AUTH0_CLIENT_ID = env.get(constants.AUTH0_CLIENT_ID)
AUTH0_CLIENT_SECRET = env.get(constants.AUTH0_CLIENT_SECRET)
AUTH0_DOMAIN = env.get(constants.AUTH0_DOMAIN)
AUTH0_BASE_URL = 'https://' + AUTH0_DOMAIN
AUTH0_AUDIENCE = env.get(constants.AUTH0_AUDIENCE)
if AUTH0_AUDIENCE is '':
    AUTH0_AUDIENCE = AUTH0_BASE_URL + '/userinfo'

app = Flask(__name__, static_url_path='/public', static_folder='./public')
app.secret_key = constants.SECRET_KEY
app.debug = True

# Connect to Database and create database session
engine = create_engine('sqlite:///itemcatalog.db',connect_args={'check_same_thread': False})
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()

@app.errorhandler(Exception)
def handle_auth_error(ex):
    response = jsonify(message=str(ex))
    response.status_code = (ex.code if isinstance(ex, HTTPException) else 500)
    return response


oauth = OAuth(app)

auth0 = oauth.register(
    'auth0',
    client_id=AUTH0_CLIENT_ID,
    client_secret=AUTH0_CLIENT_SECRET,
    api_base_url=AUTH0_BASE_URL,
    access_token_url=AUTH0_BASE_URL + '/oauth/token',
    authorize_url=AUTH0_BASE_URL + '/authorize',
    client_kwargs={
        'scope': 'openid profile',
    },
)
def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in login_session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/api/v1/catalog.json')
def showCatalogJson():
    items = session.query(CatalogItem).order_by(CatalogItem.id.desc())
    return jsonify(CatalogItems=[i.serialize for i in items])


@app.route(
    '/api/v1/categories/<int:category_id>/item/<int:catalog_item_id>/JSON')
def catalogItemJson(category_id, catalog_item_id):
    Catalog_Item = session.query(
        CatalogItem).filter_by(id=catalog_item_id).one()
    return jsonify(Catalog_Item=Catalog_Item.serialize)


@app.route('/api/v1/categories/JSON')
def categoriesJson():
    categories = session.query(Category).all()
    return jsonify(Categories=[r.serialize for r in categories])

@app.route('/')
@app.route('/categories/')
def showCatalog():
    """Returns catalog page with all categories and recently added items"""
    categories = session.query(Category).all()
    items = session.query(CatalogItem).order_by(CatalogItem.id.desc())
    quantity = items.count()
    if 'username' not in login_session:
        return render_template(
            'public_catalog.html',
            categories=categories, items=items, quantity=quantity)
    else:
        return render_template(
            'catalog.html',
            categories=categories, items=items, quantity=quantity)


@app.route('/categories/new', methods=['GET', 'POST'])
@requires_auth
def newCategory():
    """Allows user to create new category"""
    print ('i m here..')
    if request.method == 'POST':
        if 'user_id' not in login_session and 'email' in login_session:
            login_session['user_id'] = getUserID(login_session['email'])
        newCategory = Category(
            name=request.form['name'],
            user_id=login_session['user_id'])
        session.add(newCategory)
        session.commit()
        flash("New category created!", 'success')
        return redirect(url_for('showCatalog'))
    else:
        return render_template('new_category.html')


@app.route('/categories/<int:category_id>/edit/', methods=['GET', 'POST'])
@requires_auth
def editCategory(category_id):
    """Allows user to edit an existing category"""
    editedCategory = session.query(
        Category).filter_by(id=category_id).one()
    if editedCategory.user_id != login_session['user_id']:
        return "<script>function myFunction() {alert('You are not authorized!')}</script><body onload='myFunction()'>"  # noqa
    if request.method == 'POST':
        if request.form['name']:
            editedCategory.name = request.form['name']
            flash(
                'Category Successfully Edited %s' % editedCategory.name,
                'success')
            return redirect(url_for('showCatalog'))
    else:
        return render_template(
            'edit_category.html', category=editedCategory)


@app.route('/categories/<int:category_id>/delete/', methods=['GET', 'POST'])
@requires_auth
def deleteCategory(category_id):
    """Allows user to delete an existing category"""
    categoryToDelete = session.query(
        Category).filter_by(id=category_id).one()
    if categoryToDelete.user_id != login_session['user_id']:
        return "<script>function myFunction() {alert('You are not authorized!')}</script><body onload='myFunction()'>"  # noqa
    if request.method == 'POST':
        session.delete(categoryToDelete)
        flash('%s Successfully Deleted' % categoryToDelete.name, 'success')
        session.commit()
        return redirect(
            url_for('showCatalog', category_id=category_id))
    else:
        return render_template(
            'delete_category.html', category=categoryToDelete)


@app.route('/categories/<int:category_id>/')
@app.route('/categories/<int:category_id>/items/')
def showCategoryItems(category_id):
    """returns items in category"""
    category = session.query(Category).filter_by(id=category_id).one()
    categories = session.query(Category).all()
    creator = getUserInfo(category.user_id)
    items = session.query(
        CatalogItem).filter_by(
            category_id=category_id).order_by(CatalogItem.id.desc())
    quantity = items.count()
    return render_template(
        'catalog_menu.html',
        categories=categories,
        category=category,
        items=items,
        quantity=quantity,
        creator=creator)


@app.route('/categories/<int:category_id>/item/<int:catalog_item_id>/')
def showCatalogItem(category_id, catalog_item_id):
    """returns category item"""
    category = session.query(Category).filter_by(id=category_id).one()
    item = session.query(
        CatalogItem).filter_by(id=catalog_item_id).one()
    creator = getUserInfo(category.user_id)
    return render_template(
        'catalog_menu_item.html',
        category=category, item=item, creator=creator)


@app.route('/categories/item/new', methods=['GET', 'POST'])
@requires_auth
def newCatalogItem():
    categories = session.query(Category).all()
    if request.method == 'POST':
        addNewItem = CatalogItem(
            name=request.form['name'],
            description=request.form['description'],
            price=request.form['price'],
            category_id=request.form['category'],
            user_id=login_session['user_id'])
        session.add(addNewItem)
        session.commit()
        flash("New catalog item created!", 'success')
        return redirect(url_for('showCatalog'))
    else:
        return render_template('new_catalog_item.html', categories=categories)


@app.route(
    '/categories/<int:category_id>/item/<int:catalog_item_id>/edit',
    methods=['GET', 'POST'])
@requires_auth
def editCatalogItem(category_id, catalog_item_id):
    editedItem = session.query(
        CatalogItem).filter_by(id=catalog_item_id).one()
    if editedItem.user_id != login_session['user_id']:
        return "<script>function myFunction() {alert('You are not authorized!')}</script><body onload='myFunction()'>"  # noqa
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        if request.form['price']:
            editedItem.price = request.form['price']
        if request.form['category']:
            editedItem.category = request.form['category']
        session.add(editedItem)
        session.commit()
        flash("Catalog item updated!", 'success')
        return redirect(url_for('showCatalog'))
    else:
        categories = session.query(Category).all()
        return render_template(
            'edit_catalog_item.html',
            categories=categories,
            item=editedItem)


@app.route(
    '/categories/<int:category_id>/item/<int:catalog_item_id>/delete',
    methods=['GET', 'POST'])
@requires_auth
def deleteCatalogItem(category_id, catalog_item_id):
    itemToDelete = session.query(
        CatalogItem).filter_by(id=catalog_item_id).one()
    if itemToDelete.user_id != login_session['user_id']:
        return "<script>function myFunction() {alert('You are not authorized!')}</script><body onload='myFunction()'>"  # noqa
    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash('Catalog Item Successfully Deleted', 'success')
        return redirect(url_for('showCatalog'))
    else:
        return render_template(
            'delete_catalog_item.html', item=itemToDelete)



@app.route('/callback')
def callback_handling():
    auth0.authorize_access_token()
    resp = auth0.get('userinfo')
    userinfo = resp.json()
    login_session[constants.JWT_PAYLOAD] = userinfo
    login_session["user_id"] = userinfo['sub']
    login_session["username"] = userinfo ['nickname']
    login_session["email"] = userinfo['name']
    login_session['picture'] = userinfo['picture']
    return redirect('/')


# User helper functions
def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        print (user)
        return user.id
    except:
        return None


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user



@app.route('/login')
def login():
    return auth0.authorize_redirect(redirect_uri=AUTH0_CALLBACK_URL, audience=AUTH0_AUDIENCE)


@app.route('/logout')
def logout():
    login_session.clear()
    params = {'returnTo': url_for('showCatalog',_external=True), 'client_id': AUTH0_CLIENT_ID}
    print (auth0.api_base_url + '/v2/logout?' + urlencode(params))
    return redirect(auth0.api_base_url + '/v2/logout?' + urlencode(params))


@app.route('/dashboard')
@requires_auth
def dashboard():
    return render_template('dashboard.html',
                           userinfo=session[constants.PROFILE_KEY],
                           userinfo_pretty=json.dumps(session[constants.JWT_PAYLOAD], indent=4))


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=env.get('PORT', 3000))

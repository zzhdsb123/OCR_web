from app import app
from flask import render_template, request, redirect, url_for, session, jsonify
import boto3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename
from datetime import timedelta
import datetime
import os
from boto3.dynamodb.conditions import Key

# the following four image extensions are allowed
app.config["allowed_img"] = ["png", "jpg", "jpeg", "fig"]
# the maximum image size is 10m
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
key = boto3.resource('s3')
obj = key.Object('chaoshuai', 'key.txt')
app.secret_key = obj.get()['Body'].read().decode('utf-8')


def allowed_img(filename):
    # a function which determines whether a filename(extension) is allowed
    # str(filename) -> bool
    # If the file extension in 'png', 'jpg', 'jpeg' and 'gif', return True, otherwise return False
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1]
    if ext.lower() in app.config["allowed_img"]:
        return True
    else:
        return False


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    # login page
    # verify the username and password provided by the user
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        dynamodb = boto3.client('dynamodb')
        response = dynamodb.get_item(TableName='users', Key={'username': {'S': username}})
        if 'Item' not in response:
            return render_template('login.html', p=1)
        if check_password_hash(response['Item']['password']['S'], password + app.secret_key):
            session['user'] = username
            session.permanent = True
            # after 24 hours, users are required to reenter their usernames and passwords for security purposes
            app.permanent_session_lifetime = timedelta(minutes=1440)
            return redirect(url_for('user', username=username))
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':

        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        context = {
            'username_valid': 0,
            'password_valid': 0,
            'pawconfirm_valid': 0,
            'username': username
        }

        flag = False
        if not 2 <= len(username) <= 20:
            context['username_valid'] = 1
            flag = True

        if password != confirm_password:
            context['password_valid'] = 1
            flag = True

        if not 2 <= len(password) <= 20:
            context['password_valid'] = 2
            flag = True

        dynamodb = boto3.client('dynamodb')

        response = dynamodb.get_item(TableName='users', Key={'username': {'S': username}})
        if "Item" in response:
            context['username_valid'] = 2
            flag = True

        if flag:
            return render_template('register.html', **context)

        password = generate_password_hash(password + app.secret_key)

        dynamodb.put_item(
            TableName='users',
            Item={
                'username': {'S': username},
                'password': {'S': password}
            }
        )

        session['user'] = username

    context = {
        'username_valid': -1,
        'password_valid': -1,
        'pawconfirm_valid': -1
    }
    return render_template('register.html', **context)


@app.route('/user')
def user():
    if 'user' not in session:
        return redirect(url_for('index'))
    username = session['user']
    return render_template('user.html', user=username)


@app.route('/upload', methods=['GET', 'POST'])
def upload():
    # if the user are not logged in, redirect to the login page
    if 'user' not in session:
        return redirect(url_for('index'))
    username = session['user']
    # verify the extension of the image which users want to upload
    if request.method == "POST":
        try:
            file = request.files['file']
        except RequestEntityTooLarge:
            return render_template('upload_not_success.html', errorcode=3)
        if request.files:
            if file.filename == "":
                return render_template('upload_not_success.html', errorcode=1)
            if not allowed_img(file.filename):
                return render_template('upload_not_success.html', errorcode=2)
            else:
                # use a unique id to mark each image so that images with same name will not overwrite each other
                filename = secure_filename(file.filename)

                # no need to keep the original filename
                useless, ext = filename.rsplit(".", 1)
                dynamodb = boto3.client('dynamodb')
                response = dynamodb.get_item(TableName='images', Key={'image_id': {'N': '0'}})
                current_id = response['Item']['current_id']['N']
                current_id = str(int(current_id) + 1)
                name = current_id + '.' + ext
                file.save(name)
                dynamodb.put_item(
                    TableName='images',
                    Item={
                        'image_id': {'N': '0'},
                        'current_id': {'N': current_id}
                    }
                )

                dynamodb.put_item(
                    TableName='images',
                    Item={
                        'image_id': {'N': current_id},
                        'user': {'S': username},
                        'name': {'S': name},
                        'year': {'S': str(datetime.datetime.now().year)},
                        'month': {'S': str(datetime.datetime.now().month)},
                        'day': {'S': str(datetime.datetime.now().day)},
                        'date': {'S': str(datetime.datetime.now().date())}
                    }
                )
                s3 = boto3.client('s3')
                s3.upload_file(name, 'chaoshuai', 'ocr/' + name)
                os.remove(name)
        return render_template('upload_success.html')

    return render_template('upload.html')


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))


@app.route('/preview')
def preview():
    if 'user' not in session:
        return redirect(url_for('index'))
    username = session['user']
    table = boto3.resource('dynamodb').Table('images')
    response = table.scan()['Items']
    namelist = []
    for i in response:
        if 'user' in i and i['user'] == username:
            namelist.append((i['name'], i['date']))
    hists = {}
    s3 = boto3.client('s3')
    for item in namelist:
        image = item[0]
        url = s3.generate_presigned_url('get_object',
                                        Params={'Bucket': 'chaoshuai',
                                                'Key': 'ocr/' + image,
                                                })
        hists[url] = (image, item[1])
    return render_template('preview.html', hists=hists)


@app.route('/receipt_detail/<img_name>', methods=['GET', 'POST'])
def receipt_detail(img_name):
    if 'user' not in session:
        return redirect(url_for('index'))
    img_id, ext = img_name.rsplit(".", 1)
    table = boto3.resource('dynamodb').Table('Receipts')
    response = table.scan()['Items']
    hists = {}
    for item in response:
        if 'img_id' in item and item['img_id'] == img_id:
            if item['item_name'] != 'TotalPrice':
                info = {'img_id': item['img_id'],
                        'item_name': item['item_name'],
                        'price': item['price']
                        }
                item_id = item['id']
                hists[item_id] = info
            else:
                info = {'img_id': item['img_id'],
                        'item_name': item['item_name'],
                        'price': item['price']
                        }
                item_id = item['id']
                total_price = {item_id: info}
    return render_template('detail.html', hists=hists, img_id=img_id, total_price=total_price)


@app.route('/modify/<img_id>', methods=['GET', 'POST'])
def modify(img_id):
    if 'user' not in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        table = boto3.resource('dynamodb').Table('Receipts')
        response = table.scan()['Items']
        dynamodb = boto3.client('dynamodb')
        total = 0
        total_price = None
        for item in response:
            if 'img_id' in item and item['img_id'] == img_id:
                if item['item_name'] != 'TotalPrice':
                    receipt_id = item['id']
                    total += float(request.form.get('price.' + receipt_id))
                    new_item = {'item_name': {'S': request.form.get('item.' + receipt_id)},
                                'price': {'S': request.form.get('price.' + receipt_id)},
                                'id': {"S": receipt_id},
                                'img_id': {'S': item['img_id']}}
                    dynamodb.put_item(
                        TableName='Receipts',
                        Item=new_item
                    )
                else:
                    total_price = item
        receipt_id = total_price['id']
        new_item = {'item_name': {'S': request.form.get('item.' + receipt_id)},
                    'price': {'S': request.form.get('price.' + receipt_id)},
                    'id': {"S": receipt_id},
                    'img_id': {'S': total_price['img_id']}}
        dynamodb.put_item(
            TableName='Receipts',
            Item=new_item
        )
        img_name = dynamodb.get_item(TableName='images', Key={'image_id': {'N': img_id}})["Item"]['name']['S']
        # response = dynamodb.get_item(TableName='Receipts', Key={'id': {'S': receipt_id}})["Item"]
        # return response
        return redirect(url_for('receipt_detail', img_name=img_name))


@app.route('/delete')
def delete():
    pass

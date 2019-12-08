from app import app
from flask import render_template, request, redirect, url_for, session, jsonify
import boto3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename
from datetime import timedelta
import datetime
import os
from app.helper import *
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
    if 'user' in session:
        return redirect(url_for('user'))
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
        return redirect(url_for('user'))

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

                user_table = boto3.resource('dynamodb').Table('users')
                current_user = user_table.get_item(
                    Key={
                        'username': username
                    }
                )
                item = current_user['Item']
                if 'images' in current_user["Item"]:
                    item['images'].append(current_id)
                    user_table.put_item(Item=item)
                else:
                    item['images'] = [current_id]
                    user_table.put_item(Item=item)

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
    user_table = boto3.resource('dynamodb').Table('users')
    current_user = user_table.get_item(
        Key={
            'username': username
        }
    )
    if 'images' not in current_user["Item"]:
        return render_template('preview.html')
    images = current_user["Item"]["images"]
    namelist = []

    image_table = boto3.resource('dynamodb').Table('images')

    for image_id in images:
        current_image = image_table.get_item(Key={
            'image_id': int(image_id)
        })
        try:
            namelist.append(current_image["Item"])
        except KeyError:
            pass
    hists = {}
    s3 = boto3.client('s3')
    for item in namelist:
        image = item['name']
        url = s3.generate_presigned_url('get_object',
                                        Params={'Bucket': 'chaoshuai',
                                                'Key': 'ocr/' + image,
                                                })
        hists[url] = (image, item['date'], item['image_id'])
    return render_template('preview.html', hists=hists)


@app.route('/receipt_detail/<img_name>', methods=['GET', 'POST'])
def receipt_detail(img_name):
    if 'user' not in session:
        return redirect(url_for('index'))
    rd = receipt_detail_maker(img_name)
    context = rd.get_form
    if context['status'] == '0':
        return render_template('not_ready.html', img_name=img_name)
    return render_template('detail.html', **context)


@app.route('/modify/<img_id>', methods=['GET', 'POST'])
def modify(img_id):
    if 'user' not in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        editor = Receipts_tool()
        editor.edit_from_submit(form=request.form, img_id=img_id)
        return redirect(url_for('preview'))


@app.route('/delete/<img_id>/<img_name>')
def delete(img_id, img_name):
    return img_id
    client = boto3.client('s3')
    client.delete_object(Bucket='chaoshuai', Key='ocr/' + img_name)
    dynamodb = boto3.resource('dynamodb')
    table = dynamodb.Table('images')
    table.delete_item(
        Key={
            'image_id': int(img_id)
        }
    )
    table = dynamodb.Table('Receipts')
    response = table.scan()['Items']
    for i in response:
        if 'img_id' in i and i['img_id'] == img_id:
            item_id = i['id']
            table.delete_item(
                Key={
                    'id': item_id
                }
            )
    return redirect(url_for('preview'))


@app.route('/report/month_select', methods=['POST', 'GET'])
def month_select():
    if 'user' not in session:
        return redirect(url_for('index'))
    month = []
    current_month = int(datetime.datetime.now().month)
    current_year = int(datetime.datetime.now().year)
    month.append([current_year, current_month])
    for i in range(2):
        current_month -= 1
        if current_month == 0:
            current_month = 12
            current_year -= 1
        month.append([current_year, current_month])
    return render_template('select_month.html', month=month)


@app.route('/report/month_detail/')
def month_report():
    if 'user' not in session:
        return redirect(url_for('index'))
    year = request.args.get('year')
    month = request.args.get('month')
    if not year:
        year = str(datetime.datetime.now().year)
        month = str(datetime.datetime.now().month)
    username = session['user']
    cl = chart_tool()
    datas = cl.get_data_by_mounth(username, year, month)
    context = {
        'datas': datas,
        'present_year': year,
        'present_month': month,
    }
    buttons = cl.get_buttons(year, month)
    context.update(buttons)
    return render_template('month_sumary.html', **context)
    # return render_template('month_report.html', report=report)

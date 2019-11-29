import boto3
from boto3.dynamodb.conditions import Key, Attr
from flask import request,url_for

class receipt_detail_maker:
    def __init__(self, ImgnName):
        self.ImgnName = ImgnName

    def __get_cnt(self):
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table('Receipts')
        response = table.query(
            KeyConditionExpression=Key('id').eq('0')
        )
        item_id = int(response['Items'][0]['cnt']) + 1

        response = table.update_item(
            Key={
                'id': '0',
            },
            UpdateExpression="set cnt = :r",
            ExpressionAttributeValues={
                ':r': str(item_id),
            },
            ReturnValues="UPDATED_NEW"
        )
        return str(item_id)
    def __get_img_sta(self,img_id):
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table('img_stat')
        response = table.query(
            KeyConditionExpression=Key('id').eq(img_id)
        )
        sta=str(response['Items'][0]['status'])
        print(sta)
        return sta=='0'

    def get_form(self):
        img_name = self.ImgnName
        s3 = boto3.client('s3')
        img_url = s3.generate_presigned_url('get_object',
                                            Params={'Bucket': 'chaoshuai',
                                                    'Key': 'ocr/' + img_name,
                                                    })
        img_id, ext = img_name.rsplit(".", 1)
        if self.__get_img_sta(img_id):
            print('onsao')
            return {'status':'0'}
        table = boto3.resource('dynamodb').Table('Receipts')
        response = table.scan()['Items']

        cols = []
        flag=True

        for item in response:

            if 'img_id' in item and item['img_id'] == img_id:
                if item['item_name'] != 'TotalPrice':
                    col = {
                        'id':item['id'],
                        'img_id': item['img_id'],
                        'item_name': item['item_name'],
                        'price': item['price'],
                        'item_tag':item['item_tag']
                    }
                    cols.append(col)
                else:
                    flag=False
                    total_price_id=item['id']
                    total_price=item['price']
            cols=sorted(cols,key=lambda x:x['id'])

            # No total price
            # Create one
        if flag:
            total_price_id = self.__get_cnt()
            total_price = 0

            dynamodb = boto3.resource('dynamodb')
            Rtable = dynamodb.Table('Receipts')
            response = Rtable.put_item(
                Item={
                    'id': total_price_id,
                    'img_id': img_id,
                    'item_name': "TotalPrice",
                    'price': str(total_price),
                    'item_tag': " ",
                }
            )

        item_type_list=['Food','Sports','Entertainment ','Housing','Transportation','Insurance','Medical & Healthcare','Utilities','Clothing','Education']


        response={
            'status':'1',
            'cols':cols,
            'total_price_id':total_price_id,
            'total_price':total_price,
            'item_type_list':item_type_list,
            'img_id':img_id,
            'img_url':img_url,
        }
        return response

class dynamodb_tool:
    def __init__(self):
        dynamodb = boto3.resource('dynamodb')
        self.ReceiptsTable = dynamodb.Table('Receipts')

class Receipts_tool(dynamodb_tool):
    def __init__(self):
        super().__init__()
        pass

    def edit_from_submit(self,form,img_id):
        print(form)
        items={}
        table=self.ReceiptsTable
        for key,value in form.items():
            id=key.split('/')[1]
            keyi=key.split('/')[0]
            if not value:
                value=' '
            if keyi=='total_price':
                items[id] = {}
                items[id]['item_name'] = 'TotalPrice'
                items[id]['img_id'] = img_id
                items[id]['price'] = str(value)
                items[id]['item_tag'] = ' '
            else:
                if items.get(id):
                    items[id][keyi]=str(value)
                    items[id]['img_id']=img_id
                else:
                    items[id]={}
                    items[id][keyi] = str(value)
                    items[id]['img_id'] = img_id

        for key, value in items.items():
            id=key
            print(value)
            response = table.update_item(
                Key={
                    'id': id,
                },
                UpdateExpression="set item_name=:in, price=:p, item_tag=:it",
                ExpressionAttributeValues={
                    ':in': value['item_name'],
                    ':p': value['price'],
                    ':it': value['item_tag'],
                },
                ReturnValues="UPDATED_NEW"
            )

class chart_tool(dynamodb_tool):
    def __init__(self):
        super().__init__()

    def get_data_by_mounth(self,user,year,month):
        username=user
        table = boto3.resource('dynamodb').Table('images')
        response = table.scan()['Items']
        images = []
        for i in response:
            if 'user' in i and i['user'] == username and i['year'] == year and i['month'] == month:
                images.append(str(i['image_id']))
        datas=[]
        tags_cnt={}
        Sum=0.0
        receipt_table = boto3.resource('dynamodb').Table('Receipts')

        response = receipt_table.scan()['Items']
        for item in response:
            item_id=item['id']
            if not item_id=='0':
                item_name=item['item_name']
                img_id=item['img_id']
                item_tag=item['item_tag']
                item_price=item['price']
                if img_id in images and 'saving' not in item_name.lower() and 'hst' not in item_name.lower():
                    if item_tag==' ':
                        item_tag='Others'
                    if not tags_cnt.get(item_tag):
                        tags_cnt[item_tag]=float(item_price)
                        Sum+=float(item_price)
                    else:
                        tags_cnt[item_tag]+=float(item_price)
                        Sum+=float(item_price)

        for tag_name, count in tags_cnt.items():
            data={
                'tag_name':tag_name,
                'count':count/Sum*100.,
            }
            datas.append(data)
        return datas

    def get_buttons(self,year,month):
        years=['2019','2018','2017','2016','2015']
        months=['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December']
        year_buttons=[]
        month_buttons=[]
        for yeari in years:
            if yeari==year:
                button_type='btn-primary'
            else:
                button_type='btn-outline-primary'
            data={
                'text':yeari,
                'url':url_for('month_report',year=yeari,month='1'),
                'type':button_type,
            }
            year_buttons.append(data)
        for i,monthi in enumerate(months):
            if str(i+1)==month:
                button_type = 'btn-primary'
            else:
                button_type = 'btn-outline-primary'
            data = {
                'text': monthi,
                'url': url_for('month_report', year=year, month=i+1),
                'type': button_type,
            }
            month_buttons.append(data)
        contexs={
            'year_buttons':year_buttons,
            'month_buttons':month_buttons,
        }
        return contexs
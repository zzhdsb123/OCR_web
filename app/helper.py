import boto3
from boto3.dynamodb.conditions import Key, Attr
from flask import request

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

        item_type_list=['Food','Sports','Games']
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

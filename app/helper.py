import boto3
from boto3.dynamodb.conditions import Key, Attr

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

    def get_form(self):
        img_name = self.ImgnName

        img_id, ext = img_name.rsplit(".", 1)
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
                        'price': item['price']
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

        item_type_list=[" ",'Food','Sports','Games']
        response={
            'cols':cols,
            'total_price_id':total_price_id,
            'total_price':total_price,
            'item_type_list':item_type_list,
            'img_id':img_id,
        }
        return response

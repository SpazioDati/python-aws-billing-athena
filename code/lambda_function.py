import re
from time import sleep
from zipfile import ZipFile

import boto3
import config

s3_client = boto3.client('s3')
s3_resource = boto3.resource('s3')
athena_client = boto3.client('athena')

key_regex = r'^(?:\d*)-aws-billing-detailed-' \
            r'line-items-with-resources-and-tags-(\d{4})-(\d{2})\.csv\.zip$'
output_key = "{folder}/year={year}/month={month}/aws-billing.csv"


def extract_zip(input_file):
    input_zip = ZipFile(input_file)
    return [input_zip.read(name) for name in input_zip.namelist()][0]


def athena_query(client, query):
    query_id = client.start_query_execution(
        QueryString=query,
        QueryExecutionContext={
            'Database': config.DATABASE
        },
        ResultConfiguration={
            'OutputLocation': config.BUCKET
        }
    ).get('QueryExecutionId')
    wait_for_success(client, query_id)


def wait_for_success(client, query_id):
    slept = 0
    while client.get_query_execution(
                QueryExecutionId=query_id) != 'SUCCESS' and slept < 20:
        sleep(2)
        slept += 2


def lambda_handler(event, context):
    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']

        if re.search(key_regex, key):
            extracted = re.search(key_regex, key)
            year = extracted.group(1)
            month = extracted.group(2)

            with open('/tmp/temp.zip', 'wb+') as input_file:
                s3_client.download_fileobj(bucket, key, input_file)
                input_file = extract_zip(input_file)
                s3_resource.Object(bucket, output_key.format(
                    year=year, month=month, folder=config.FOLDER)).put(
                    Body=input_file)

            athena_query(athena_client, 'DROP TABLE aws_billing')

            with open("table_creation.txt", "r") as myfile:
                query = myfile.read().replace('\n', '').format(
                    bucket=config.BUCKET, folder=config.FOLDER)

            athena_query(athena_client, query)

            athena_query(athena_client, 'MSCK REPAIR TABLE aws_billing')

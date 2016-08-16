#!/usr/bin/env python

#
# f5-aws-autoscale.py
#

# from __future__ import print_function

#  Standard
import json

#  AWS
import boto3
import logging

#  F5
from f5.bigip import ManagementRoot

print('Loading function')
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

def lambda_handler(event, context):
# event - AWS Lambda uses this parameter to pass in event data to the handler. This parameter is usually of the Python dict type. It can also be list, str, int, float, or NoneType type.
# context - AWS Lambda uses this parameter to provide runtime information to your handler. This parameter is of the LambdaContext type.
# Optionally, the handler can return a value. What happens to the returned value depends on the invocation type you use when invoking the Lambda function:
#     If you use the RequestResponse invocation type (synchronous execution), AWS Lambda returns the result of the Python function call to the client invoking the Lambda function (in the HTTP response to the invocation request, serialized into JSON). For example, AWS Lambda console uses the RequestResponse invocation type, so when you invoke the function using the console, the console will display the returned value.
#     If the handler does not return anything, AWS Lambda returns null.
#     If you use the Event invocation type (asynchronous execution), the value is discarded.
    # print(event['key1'])
    # return some_value
    # raise Exception('Something went wrong')
    logger.info('Got Event{}'.format(event))

    #  For each F5 instnace, tag the instance with the name(s) of the AutoScalingGroup configured within.

    #  Start AWS API clients
    logger.debug('Starting AWS API clients...')
    ec2 = boto3.client('ec2')
#    autoscaling = boto3.client('autoscaling')

    #  Get list of F5 devices by AMI
    logger.debug('Getting list of F5 images...')
    f5_images = ec2.describe_images(Filters=[
        {
            'Name': 'name',
            'Values': ['F5 Networks*',],
        },
    ])

    #  Filter list of F5 images to just a list of AMIs
    f5_amis = [image['ImageId'] for image in f5_images['Images']]

    #  Get list of instances using F5 AMIs in region
    logger.debug('Getting list of F5 instances...')
    f5_instances = ec2.describe_instances(Filters=[
        {
            'Name': 'image-id',
            'Values': f5_amis,
        },
    ])

    #  Go into each instance and check for a AutoScaleGroup
    for instance in f5_instances['Reservations'][0]['Instances']:
        #  Connect to F5 instance using REST API
        logger.debug('['+instance['InstanceId']+'] Connecting to F5 API...')
        bigip = f5_connect(server=instance['NetworkInterfaces'][0]['PrivateDnsName'], user='ec2-user', password='ec2-user')

        #  Get list of pools and their AutoScalingGroupId
        logger.debug('['+instance['InstanceId']+'] Getting list of pools...')
        pools = bigip.tm.ltm.pools.get_collection()
        add_tags = { 'f5:pool:'+pool.name: 'aws:AutoScalingGroup:'+pool.autoscaleGroupId for pool in pools if hasattr(pool, 'autoscaleGroupId')}

        #  Add/Update tags on instance (any result from above will need tag or already has one)
        logger.debug('['+instance['InstanceId']+'] Adding tags...')
        ec2.create_tags(Resources=[instance['InstanceId']], Tags=dict_to_tags(add_tags))
        #  Remove orphaned tags ('f5:pool' tags that are not in add_tags means the pool no longer exists or no longer is associated to an ASG)

        remove_tags = {key: value for key, value in tags_to_dict(instance['Tags']).iteritems() if key.startswith('f5:pool:') and key not in add_tags}
        logger.debug('['+instance['InstanceId']+'] Removing tags if necessary...')
        if remove_tags:
            ec2.delete_tags(Resources=[instance['InstanceId']], Tags=dict_to_tags(remove_tags))

        logger.debug('['+instance['InstanceId']+'] Completed...')

    logger.debug('Complete.')
    return None

def f5_connect(*args, **kwargs):
    return ManagementRoot(kwargs['server'], kwargs['user'], kwargs['password'])

def dict_to_tags(mydict):
    return [{'Key': key, 'Value': value} for key, value in mydict.iteritems()]

def tags_to_dict(mytags):
    return {tag['Key']: tag['Value'] for tag in mytags}

if __name__ == '__main__':
    lambda_handler(None, None)

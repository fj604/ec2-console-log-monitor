#!/usr/bin/python3

"""
Monitor AWS console logs on tagged EC2 instances and save them to S3.

These logs may help troubleshoot Linux kernel panic messages that may
otherwise be lost due to https://access.redhat.com/solutions/2890881.

Requires IAM policy below. This can be assigned to EC2 instance role
or IAM user.
Replace my-bucket-name with the actual bucket name.

{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeInstances",
                "ec2:GetConsoleOutput"
            ],
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": "s3:PutObject",
            "Resource": "arn:aws:s3:::my-bucket-name/*"
        }
    ]
}

usage: monitor_console.py [-h] [-f] [-p] [-q] tag region bucket interval

positional arguments:
  tag          tag assigned to monitored instances
  region       AWS region to monitor
  bucket       S3 bucket name to store logs
  interval     monitoring interval in seconds

optional arguments:
  -h, --help   show this help message and exit
  -f, --file   write console logs to local files
  -p, --print  print console logs to standard output
  -q, --quiet  do not show informational logging
"""


__version__ = "1.0"


import boto3
import time
import logging
import argparse


def out_to_file(instanceId, timestamp, output):
    """Output console log to file."""
    filename = (instanceId + "_"
                + timestamp.strftime('%Y-%m-%dT%H%M%S'))
    with open(filename, "w") as outfile:
        logging.info(f"Writing output to file {filename}")
        print(output, file=outfile)
        outfile.close()


def out_to_print(instanceId, timestamp, output):
    """Output console log to standard output."""
    print("====================================")
    print("Instance ID:", instanceId)
    print("Timestamp:", timestamp)
    print("------------------------------------")
    print(output)


def out_to_s3(bucket, instanceId, timestamp, output):
    """Output console log to S3 bucket."""
    key = f"{instanceId}/{timestamp}"
    logging.info(f"Writing key {key} to "
                 + f"S3 bucket {bucket}")
    try:
        s3.put_object(Bucket=bucket, Key=key,
                      Body=output)
    except Exception as e:
        logging.error("Cannot put object to S3 bucket"
                      + bucket + f":{e}")


parser = argparse.ArgumentParser()
parser.add_argument("tag", type=str,
                    help="tag assigned to monitored instances")
parser.add_argument("region", type=str,
                    help="AWS region to monitor")
parser.add_argument("bucket", type=str,
                    help="S3 bucket name to store logs")
parser.add_argument("interval", type=int,
                    help="monitoring interval in seconds")
parser.add_argument("-f", "--file", action="store_true",
                    help="write console logs to local files")
parser.add_argument("-p", "--print", action="store_true",
                    help="print console logs to standard output")
parser.add_argument("-q", "--quiet", action="store_true",
                    help="do not show informational logging")
args = parser.parse_args()

if args.quiet:
    loglevel = logging.WARNING
else:
    loglevel = logging.INFO
logging.basicConfig(level=loglevel)

ec2 = boto3.client("ec2", region_name=args.region)
s3 = boto3.client("s3", region_name=args.region)

filters = [{"Name": "tag-key", "Values": [args.tag]}]
last_update = {}

while True:
    logging.info("Retrieving instances")
    try:
        reservations = ec2.describe_instances(Filters=filters)["Reservations"]
    except Exception as e:
        logging.error(f"Cannot list instances: {e}")
        time.sleep(args.interval)
        continue
    for reservation in reservations:
        instances = reservation["Instances"]
        logging.debug(instances)
        for instance in instances:
            instanceId = instance["InstanceId"]
            logging.info(f"Retrieving console log for instance {instanceId}")
            try:
                response = ec2.get_console_output(InstanceId=instanceId)
            except Exception as e:
                logging.error("Cannot retrieve log for instance "
                              + instanceId + f":{e}")
                continue
            timestamp = response["Timestamp"]
            if (
                instanceId in last_update
                and last_update[instanceId] == timestamp
               ):
                logging.info(f"No updates since {timestamp}")
            else:
                logging.info(f"Console updated {timestamp}")
                last_update[instanceId] = response["Timestamp"]
                if "Output" in response:
                    output = response["Output"]
                    out_to_s3(args.bucket, instanceId, timestamp, output)
                    if args.print:
                        out_to_print(instanceId, timestamp, output)
                    if args.file:
                        out_to_file(instanceId, timestamp, output)
                else:
                    logging.warning(f"No console output "
                                    + "received for instance "
                                    + instanceId)
    logging.info(f"Sleeping for {args.interval} seconds, "
                 + "press Ctrl+C to interrupt...")
    time.sleep(args.interval)

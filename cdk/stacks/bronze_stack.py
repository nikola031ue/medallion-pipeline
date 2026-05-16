import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_sqs as sqs
from constructs import Construct


class BronzeStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        vpc: ec2.Vpc,
        lambda_sg: ec2.SecurityGroup,
        bucket: s3.Bucket,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        dlq = sqs.Queue(
            self,
            "HnFetcherDlq",
            queue_name="hn-fetcher-dlq",
            retention_period=cdk.Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
        )

        self.hn_fetcher = lambda_.Function(
            self,
            "HnFetcher",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(
                "../lambdas/bronze/hn_fetcher",
                bundling=cdk.BundlingOptions(
                    image=lambda_.Runtime.PYTHON_3_11.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install -r requirements.txt -t /asset-output && cp -r . /asset-output",
                    ],
                ),
            ),
            vpc=vpc,
            security_groups=[lambda_sg],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            timeout=cdk.Duration.minutes(15),
            memory_size=512,
            environment={
                "BUCKET_NAME": bucket.bucket_name,
                "HN_API_BASE": "https://hn.algolia.com/api/v1",
                "HN_ITEM_TYPES": "story,comment,ask_hn,show_hn,job,poll",
                "BRONZE_PREFIX": "bronze/hacker-news",
            },
            dead_letter_queue=dlq,
        )

        bucket.grant_put(self.hn_fetcher, "bronze/hacker-news/*")

        rule = events.Rule(
            self,
            "DailyHnTrigger",
            schedule=events.Schedule.cron(hour="0", minute="0"),
            description="Daily trigger for HN bronze fetcher at midnight UTC",
        )
        rule.add_target(targets.LambdaFunction(self.hn_fetcher))

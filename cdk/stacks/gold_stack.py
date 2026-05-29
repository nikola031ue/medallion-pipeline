import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from constructs import Construct


class GoldStack(cdk.Stack):
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

        self.metrics_calculator = lambda_.DockerImageFunction(
            self,
            "MetricsCalculator",
            code=lambda_.DockerImageCode.from_image_asset(
                "../lambdas/gold/metrics_calculator"
            ),
            vpc=vpc,
            security_groups=[lambda_sg],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            timeout=cdk.Duration.minutes(15),
            memory_size=1024,
            environment={
                "BUCKET_NAME": bucket.bucket_name,
                "BRONZE_HN_PREFIX": "bronze/hacker-news",
                "BRONZE_TWITTER_KEY": "bronze/twitter/covid_tweets.csv",
                "SILVER_PREFIX": "silver",
                "GOLD_PREFIX": "gold",
            },
        )

        bucket.grant_read(self.metrics_calculator, "bronze/hacker-news/*")
        bucket.grant_read(self.metrics_calculator, "bronze/twitter/*")
        bucket.grant_read(self.metrics_calculator, "silver/*")
        bucket.grant_read_write(self.metrics_calculator, "gold/*")

        rule = events.Rule(
            self,
            "DailyMetricsTrigger",
            schedule=events.Schedule.cron(hour="3", minute="0"),
            description="Daily trigger for gold metrics calculator at 3am UTC",
        )
        rule.add_target(targets.LambdaFunction(self.metrics_calculator))

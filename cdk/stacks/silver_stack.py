import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from constructs import Construct


class SilverStack(cdk.Stack):
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

        self.hn_normalizer = lambda_.DockerImageFunction(
            self,
            "HnNormalizer",
            code=lambda_.DockerImageCode.from_image_asset(
                "../lambdas/silver/hn_normalizer"
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
                "BRONZE_PREFIX": "bronze/hacker-news",
                "SILVER_POSTS_PREFIX": "silver/posts",
                "SILVER_USERS_PREFIX": "silver/users",
                "HN_ITEM_TYPES": "story,comment,ask_hn,show_hn,job,poll",
            },
        )

        bucket.grant_read(self.hn_normalizer, "bronze/hacker-news/*")
        bucket.grant_read_write(self.hn_normalizer, "silver/posts/*")
        bucket.grant_read_write(self.hn_normalizer, "silver/users/*")

        rule = events.Rule(
            self,
            "DailyHnNormalizeTrigger",
            schedule=events.Schedule.cron(hour="2", minute="0"),
            description="Daily trigger for HN silver normalizer at 2am UTC",
        )
        rule.add_target(targets.LambdaFunction(self.hn_normalizer))

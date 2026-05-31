import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_stepfunctions as sfn
from aws_cdk import aws_stepfunctions_tasks as tasks
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

        self.twitter_normalizer = lambda_.DockerImageFunction(
            self,
            "TwitterNormalizer",
            code=lambda_.DockerImageCode.from_image_asset(
                "../lambdas/silver/twitter_normalizer"
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
                "BRONZE_KEY": "bronze/twitter/covid_tweets.csv",
                "SILVER_POSTS_PREFIX": "silver/posts",
                "SILVER_USERS_PREFIX": "silver/users",
            },
        )

        bucket.grant_read(self.twitter_normalizer, "bronze/twitter/*")
        bucket.grant_read_write(self.twitter_normalizer, "silver/posts/*")
        bucket.grant_read_write(self.twitter_normalizer, "silver/users/*")

        # Step Functions
        hn_task = tasks.LambdaInvoke(self, "RunHnNormalizer", lambda_function=self.hn_normalizer)
        hn_task.add_retry(
            max_attempts=2,
            interval=cdk.Duration.seconds(30),
            backoff_rate=2,
            errors=["States.TaskFailed", "Lambda.ServiceException"],
        )
        hn_task.add_catch(
            sfn.Pass(self, "HnNormalizerFailed"),
            errors=["States.ALL"],
            result_path="$.hn_error",
        )

        twitter_task = tasks.LambdaInvoke(self, "RunTwitterNormalizer", lambda_function=self.twitter_normalizer)
        twitter_task.add_retry(
            max_attempts=2,
            interval=cdk.Duration.seconds(30),
            backoff_rate=2,
            errors=["States.TaskFailed", "Lambda.ServiceException"],
        )
        twitter_task.add_catch(
            sfn.Pass(self, "TwitterNormalizerFailed"),
            errors=["States.ALL"],
            result_path="$.twitter_error",
        )

        self.data_quality_calculator = lambda_.DockerImageFunction(
            self,
            "DataQualityCalculator",
            code=lambda_.DockerImageCode.from_image_asset(
                "../lambdas/gold/data_quality"
            ),
            vpc=vpc,
            security_groups=[lambda_sg],
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            timeout=cdk.Duration.minutes(10),
            memory_size=512,
            environment={
                "BUCKET_NAME": bucket.bucket_name,
                "SILVER_PREFIX": "silver",
                "GOLD_PREFIX": "gold",
            },
        )

        bucket.grant_read(self.data_quality_calculator, "silver/*")
        bucket.grant_read_write(self.data_quality_calculator, "gold/data_quality_kpi/*")

        data_quality_task = tasks.LambdaInvoke(
            self, "DataQualityKPI", lambda_function=self.data_quality_calculator
        )
        data_quality_task.add_retry(
            max_attempts=2,
            interval=cdk.Duration.seconds(30),
            backoff_rate=2,
            errors=["States.TaskFailed", "Lambda.ServiceException"],
        )
        data_quality_task.add_catch(
            sfn.Pass(self, "DataQualityFailed"),
            errors=["States.ALL"],
            result_path="$.data_quality_error",
        )

        parallel = sfn.Parallel(self, "NormalizeBothSources", comment="HN i Twitter normalizacija paralelno")
        parallel.branch(hn_task)
        parallel.branch(twitter_task)

        self.state_machine = sfn.StateMachine(
            self,
            "SilverStateMachine",
            state_machine_name="silver-normalization",
            definition_body=sfn.DefinitionBody.from_chainable(parallel.next(data_quality_task)),
            timeout=cdk.Duration.minutes(45),
        )

        rule = events.Rule(
            self,
            "DailyHnNormalizeTrigger",
            schedule=events.Schedule.cron(hour="2", minute="0"),
            description="Daily trigger for HN silver normalizer at 2am UTC",
        )
        rule.add_target(targets.LambdaFunction(self.hn_normalizer))

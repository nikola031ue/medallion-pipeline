import aws_cdk as cdk
from aws_cdk import aws_s3 as s3
from constructs import Construct


class DataLakeStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.bucket = s3.Bucket(
            self,
            "SocialMediasBucket",
            bucket_name="social-medias",
            versioned=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
            auto_delete_objects=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,

        )

        cdk.CfnOutput(self, "BucketName", value=self.bucket.bucket_name)
        cdk.CfnOutput(self, "BronzePrefix", value=f"s3://{self.bucket.bucket_name}/bronze/")
        cdk.CfnOutput(self, "SilverPrefix", value=f"s3://{self.bucket.bucket_name}/silver/")
        cdk.CfnOutput(self, "GoldPrefix", value=f"s3://{self.bucket.bucket_name}/gold/")

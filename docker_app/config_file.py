class Config:
    # Stack name
    # Change this value if you want to create a new instance of the stack
    STACK_NAME = "Streamlit-Agents-App"
    
    # Put your own custom value here to prevent ALB to accept requests from
    # other clients that CloudFront. You can choose any random string.
    CUSTOM_HEADER_VALUE = "streamlit_agent_app_a3q4fz"    
    
    # ID of Secrets Manager containing cognito parameters
    # When you delete a secret, you cannot create another one immediately
    # with the same name. Change this value if you destroy your stack and need
    # to recreate it with the same STACK_NAME.
    SECRETS_MANAGER_ID = f"{STACK_NAME}ParamCognitoSecret20250224"

    # AWS region in which you want to deploy the cdk stack
    DEPLOYMENT_REGION = "us-east-1"

    # If Bedrock is not activated in us-east-1 in your account, set this value
    # accordingly
    BEDROCK_REGION = "us-east-1"

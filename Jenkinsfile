pipeline {
    agent any
 
    environment {
        NAMESPACE = "teamsync"
    }
 
    stages {
 
        stage('Verify Deployment') {
            steps {
                sh '''
                oc rollout status deploy/frontdms -n ${NAMESPACE}
                oc rollout status deploy/gateway-deployment -n ${NAMESPACE}
                '''
            }
        }
 
        stage('Install Dependencies') {
            steps {
                sh '''
                pip3 install -r requirements.txt
                '''
            }
        }
 
        stage('Run Login Smoke Test') {
            steps {
                sh '''
                mkdir -p reports
 
                pytest tests/login/ \
                -v \
                --html=reports/report.html \
                --self-contained-html
                '''
            }
        }
    }
 
    post {
 
        always {
 
            publishHTML([
                allowMissing: true,
                alwaysLinkToLastBuild: true,
                keepAll: true,
                reportDir: 'reports',
                reportFiles: 'report.html',
                reportName: 'Smoke Test Report'
            ])
        }
 
        success {
            echo 'Smoke Test Passed'
        }
 
        failure {
            echo 'Smoke Test Failed'
        }
    }
}
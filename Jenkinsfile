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
 
        stage('Verify Python Packages') {
            steps {
                sh '''
                python3 --version
                pip3 --version
                playwright --version
                '''
            }
        }
 
        stage('Run Login Smoke Test') {
            steps {
                sh '''
                mkdir -p reports
 
                pytest tests/login/ tests/upload/ tests/share tests/creation/ tests/rename/ tests/move/ tests/copy_paste tests/delete/ \
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
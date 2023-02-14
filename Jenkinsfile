properties([
    buildDiscarder(
        logRotator(
            artifactDaysToKeepStr: '',
            artifactNumToKeepStr: '',
            daysToKeepStr: '14',
            numToKeepStr: '10',
        )
    ),
    // Make new builds terminate existing builds
    disableConcurrentBuilds(
        abortPrevious: true,
    )
])
pipeline {
    agent {
        // Run as root to avoid permission issues when creating files.
        // To run on a specific node, e.g. for a specific architecture, add `label '...'`.
        docker {
            alwaysPull true
            image 'lsstts/develop-env:develop'
            args "--entrypoint=''"
        }
    }
    environment {
        // Python module name.
        MODULE_NAME = "lsst.ts.ess.controller"
        // Product name for documentation upload; the associated
        // documentation site is `https://{DOC_PRODUCT_NAME}.lsst.io`.
        DOC_PRODUCT_NAME = "ts-ess-controller"

        WORK_BRANCHES = "${GIT_BRANCH} ${CHANGE_BRANCH} develop"
        LSST_IO_CREDS = credentials('lsst-io')
        XML_REPORT_PATH = 'jenkinsReport/report.xml'
    }
    stages {
        stage ('Update branches of required packages') {
            steps {
                // When using the docker container, we need to change the WHOME path
                // to WORKSPACE to have the authority to install the packages.
                withEnv(["WHOME=${env.WORKSPACE}"]) {
                    sh """
                        source /home/saluser/.setup_dev.sh || echo "Loading env failed; continuing..."

                        # Update required packages
                        cd /home/saluser/repos/ts_utils
                        /home/saluser/.checkout_repo.sh ${WORK_BRANCHES}
                        git pull

                        cd /home/saluser/repos/ts_tcpip
                        /home/saluser/.checkout_repo.sh ${WORK_BRANCHES}
                        git pull

                        cd /home/saluser/repos
                        git clone https://github.com/lsst-ts/ts_ess_common.git
                        cd ts_ess_common
                        /home/saluser/.checkout_repo.sh ${WORK_BRANCHES}
                        git pull
                        eups declare -r . -t current
                    """
                }
            }
        }
        stage('Run unit tests') {
            steps {
                withEnv(["WHOME=${env.WORKSPACE}"]) {
                    sh """
                        source /home/saluser/.setup_dev.sh || echo "Loading env failed; continuing..."
                        setup -r .
                        pytest --cov-report html --cov=${env.MODULE_NAME} --junitxml=${env.XML_REPORT_PATH}
                    """
                }
            }
        }
        stage('Build documentation') {
            steps {
                withEnv(["WHOME=${env.WORKSPACE}"]) {
                    sh """
                        source /home/saluser/.setup_dev.sh || echo "Loading env failed; continuing..."
                        setup -r .
                        package-docs build
                    """
                }
            }
        }
        stage('Try to upload documentation') {
            steps {
                withEnv(["WHOME=${env.WORKSPACE}"]) {
                    catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
                        sh '''
                            source /home/saluser/.setup_dev.sh || echo "Loading env failed; continuing..."
                            setup -r .
                            ltd -u ${LSST_IO_CREDS_USR} -p ${LSST_IO_CREDS_PSW} upload \
                                --product ${DOC_PRODUCT_NAME} --git-ref ${GIT_BRANCH} --dir doc/_build/html
                        '''
                    }
                }
            }
        }
    }
    post {
        always {
            // The path of xml needed by JUnit is relative to the workspace.
            junit 'jenkinsReport/*.xml'

            // Publish the HTML report.
            publishHTML (
                target: [
                    allowMissing: false,
                    alwaysLinkToLastBuild: false,
                    keepAll: true,
                    reportDir: 'jenkinsReport',
                    reportFiles: 'index.html',
                    reportName: "Coverage Report"
                ]
            )
        }
        cleanup {
            // Clean up the workspace.
            deleteDir()
        }
    }
}

import {spawnSync} from 'node:child_process'
const python=process.env.PYTHON|| (process.platform==='win32'?'python':'python3')
const jobs=[[process.execPath,['scripts/check_node.mjs']],[python,['-B','scripts/check_python.py']],[process.execPath,['--test','scripts/test_platform.mjs','scripts/test_bridge_channel.mjs','scripts/test_local_connector.mjs','scripts/test_cloud_runtime.mjs']]]
for(const name of ['test_challenge_rules','test_desheng_leader','test_control_queue','test_arm_devices','test_teleop_lifecycle','test_connector_config','test_connector_access','test_cloud_deploy'])jobs.push([python,['-B',`scripts/${name}.py`]])
for(const [command,args] of jobs){const result=spawnSync(command,args,{stdio:'inherit',env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});if(result.status!==0)process.exit(result.status||1)}

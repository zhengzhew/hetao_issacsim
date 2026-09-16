$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$root = Split-Path $PSScriptRoot
$destination = Join-Path $root 'web\audio'
New-Item -ItemType Directory -Force -Path $destination | Out-Null
$prompts = [ordered]@{
    welcome='你好！我是小芽。先选一个想去的地方吧。'
    partner='世界选好啦！现在选一位机器人伙伴。'
    explore='准备好啦！按住方向按钮移动，松开就停。'
    drive='按住方向按钮移动，松开就停。'
    camera='按住箭头转一转、拉近看看。'
    stop='停一停，观察一下周围吧。'
    ready='实验室准备好啦！选好伙伴就能出发。'
    preparing='小芽正在准备实验室。等一等，马上就好。'
    retry='没关系，实验室需要一点帮助。请叫老师来看看吧。'
}
$worlds=[ordered]@{warehouse='小小仓库';maze='货架迷宫';room='温馨小屋';grid='自由练习场'}
foreach($entry in $worlds.GetEnumerator()){$prompts['scene-'+$entry.Key]='选中了'+$entry.Value+'！点绿色按钮，去找机器人伙伴。'}
$robots=[ordered]@{jetbot='NVIDIA Jetbot';carter='NVIDIA Carter v1';nova='NVIDIA Nova Carter';kaya='NVIDIA Kaya'}
foreach($entry in $robots.GetEnumerator()){$prompts['robot-'+$entry.Key]='选中了'+$entry.Value+'！准备好就一起出发。'}
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SelectVoice('Microsoft Huihui Desktop')
$synth.Rate = 0
$lookup = [ordered]@{}
try {
    foreach($entry in $prompts.GetEnumerator()) {
        $path=Join-Path $destination ($entry.Key+'.wav')
        $synth.SetOutputToWaveFile($path)
        $synth.Speak($entry.Value)
        $synth.SetOutputToNull()
        $lookup[$entry.Value]='/audio/'+$entry.Key+'.wav'
    }
} finally {$synth.Dispose()}
$json=$lookup | ConvertTo-Json
[IO.File]::WriteAllText((Join-Path $root 'web\voice-guides.js'),('export const voiceGuides = '+$json+';'),[Text.UTF8Encoding]::new($false))
Write-Output ('Generated '+$lookup.Count+' Chinese voice guides.')

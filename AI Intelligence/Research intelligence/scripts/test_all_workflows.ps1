$ErrorActionPreference = "Continue"

$BASE = "http://127.0.0.1:8888"
$LM = "http://127.0.0.1:1234"

$Results = @()

function Test-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    Write-Host ""
    Write-Host ("=" * 78) -ForegroundColor DarkGray
    Write-Host $Name -ForegroundColor Cyan
    Write-Host ("=" * 78) -ForegroundColor DarkGray

    $start = Get-Date

    try {
        $result = & $Action

        $elapsed = ((Get-Date) - $start).TotalSeconds

        Write-Host "PASS  $Name  [$([math]::Round($elapsed,2))s]" -ForegroundColor Green

        $script:Results += [PSCustomObject]@{
            Test    = $Name
            Status  = "PASS"
            Seconds = [math]::Round($elapsed,2)
            Detail  = "OK"
        }

        return $result
    }
    catch {
        $elapsed = ((Get-Date) - $start).TotalSeconds

        Write-Host "FAIL  $Name  [$([math]::Round($elapsed,2))s]" -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Yellow

        if ($_.ErrorDetails.Message) {
            Write-Host $_.ErrorDetails.Message -ForegroundColor DarkYellow
        }

        $script:Results += [PSCustomObject]@{
            Test    = $Name
            Status  = "FAIL"
            Seconds = [Math]::Round($elapsed,2)
            Detail  = $_.Exception.Message
        }

        return $null
    }
}

function Show-Json {
    param($Object)

    if ($null -ne $Object) {
        $Object | ConvertTo-Json -Depth 8
    }
}

Write-Host ""
Write-Host "==============================================================" -ForegroundColor Magenta
Write-Host " OAU THESIS BANK - RESEARCH INTELLIGENCE SMOKE TEST" -ForegroundColor Magenta
Write-Host "==============================================================" -ForegroundColor Magenta
Write-Host ""
Write-Host "AI service : $BASE"
Write-Host "LM Studio  : $LM"
Write-Host ""

# ------------------------------------------------------------------
# 1. AI SERVICE HEALTH
# ------------------------------------------------------------------

$health = Test-Step "01 - AI service health" {
    $r = Invoke-RestMethod "$BASE/health" -TimeoutSec 15

    if ($r.status -ne "ok") {
        throw "Health status is not ok."
    }

    Show-Json $r
    return $r
}

# ------------------------------------------------------------------
# 2. DIAGNOSTICS
# ------------------------------------------------------------------

$diagnostics = Test-Step "02 - Full diagnostics" {
    $r = Invoke-RestMethod "$BASE/api/ai/diagnostics" -TimeoutSec 30

    Show-Json $r

    if ($r.database.ok -ne $true) {
        throw "Database check failed."
    }

    if ($r.llm.ok -ne $true) {
        throw "LM Studio check failed."
    }

    return $r
}

# ------------------------------------------------------------------
# 3. DATABASE DIRECT TEST
# ------------------------------------------------------------------

Test-Step "03 - Database container reachable" {
    $tcp = Test-NetConnection 127.0.0.1 -Port 5432 -WarningAction SilentlyContinue

    if (-not $tcp.TcpTestSucceeded) {
        throw "PostgreSQL port 5432 is not reachable."
    }

    Write-Host "PostgreSQL :5432 reachable" -ForegroundColor Green
}

# ------------------------------------------------------------------
# 4. LM STUDIO MODELS
# ------------------------------------------------------------------

$models = Test-Step "04 - LM Studio model registry" {
    $r = Invoke-RestMethod "$LM/v1/models" -TimeoutSec 20

    Show-Json $r

    if (-not $r.data) {
        throw "LM Studio returned no models."
    }

    $ids = @($r.data | ForEach-Object { $_.id })

    Write-Host ""
    Write-Host "Models found:" -ForegroundColor White

    foreach ($id in $ids) {
        Write-Host "  - $id" -ForegroundColor Gray
    }

    return $r
}

# ------------------------------------------------------------------
# 5. QWEN DIRECT GENERATION
# ------------------------------------------------------------------

Test-Step "05 - Qwen direct generation through LM Studio" {

    $model = "patataaliena/qwen2.5-vl-7b-instruct"

    $body = @{
        model = $model
        messages = @(
            @{
                role = "user"
                content = "Reply with exactly: QWEN_SMOKE_TEST_OK"
            }
        )
        temperature = 0
        max_tokens = 30
        stream = $false
    } | ConvertTo-Json -Depth 8

    $r = Invoke-RestMethod `
        -Uri "$LM/v1/chat/completions" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 120

    Show-Json $r

    $text = $r.choices[0].message.content

    if (-not $text) {
        throw "Qwen returned an empty response."
    }

    Write-Host ""
    Write-Host "Qwen response: $text" -ForegroundColor Green
}

# ------------------------------------------------------------------
# 6. LAYA DIRECT GENERATION
# ------------------------------------------------------------------

Test-Step "06 - Laya direct generation through LM Studio" {

    $model = "laya-multilingual"

    $body = @{
        model = $model
        messages = @(
            @{
                role = "user"
                content = "Reply with exactly: LAYA_SMOKE_TEST_OK"
            }
        )
        temperature = 0
        max_tokens = 30
        stream = $false
    } | ConvertTo-Json -Depth 8

    $r = Invoke-RestMethod `
        -Uri "$LM/v1/chat/completions" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 120

    Show-Json $r

    $text = $r.choices[0].message.content

    if (-not $text) {
        throw "Laya returned an empty response."
    }

    Write-Host ""
    Write-Host "Laya response: $text" -ForegroundColor Green
}

# ------------------------------------------------------------------
# 7. EMBEDDING ENDPOINT
# ------------------------------------------------------------------

Test-Step "07 - LM Studio embedding endpoint" {

    $body = @{
        model = "text-embedding-nomic-embed-text-v1.5"
        input = "research intelligence smoke test"
    } | ConvertTo-Json -Depth 5

    $r = Invoke-RestMethod `
        -Uri "$LM/v1/embeddings" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 120

    if (-not $r.data) {
        throw "No embedding returned."
    }

    $vector = $r.data[0].embedding

    Write-Host "Embedding dimensions: $($vector.Count)" -ForegroundColor Green
}

# ------------------------------------------------------------------
# 8. RAG QUERY
# ------------------------------------------------------------------

Test-Step "08 - RAG query" {

    $body = @{
        query = "What is the main research problem addressed by this thesis?"
        thesis_id = 12
        top_k = 5
    } | ConvertTo-Json -Depth 8

    $r = Invoke-RestMethod `
        -Uri "$BASE/api/ai/rag-query" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 180

    Show-Json $r

    if (-not $r) {
        throw "RAG returned no response."
    }
}

# ------------------------------------------------------------------
# 9. SUMMARY
# ------------------------------------------------------------------

Test-Step "09 - Thesis summary" {

    $r = Invoke-RestMethod `
        -Uri "$BASE/api/ai/summarize?thesis_id=12" `
        -Method POST `
        -TimeoutSec 240

    Show-Json $r

    if (-not $r) {
        throw "Summary returned no response."
    }
}

# ------------------------------------------------------------------
# 10. RESEARCH GAPS
# ------------------------------------------------------------------

Test-Step "10 - Research gap detection" {

    $r = Invoke-RestMethod `
        -Uri "$BASE/api/ai/detect-gaps?topic=nlp" `
        -Method GET `
        -TimeoutSec 240

    Show-Json $r

    if (-not $r) {
        throw "Gap detection returned no response."
    }
}

# ------------------------------------------------------------------
# 11. RECOMMENDATIONS
# ------------------------------------------------------------------

Test-Step "11 - Research recommendations" {

    $r = Invoke-RestMethod `
        -Uri "$BASE/api/ai/recommend?user_id=student_1&top_k=5" `
        -Method GET `
        -TimeoutSec 180

    Show-Json $r

    if (-not $r) {
        throw "Recommendation endpoint returned no response."
    }
}

# ------------------------------------------------------------------
# 12. SIMILARITY
# ------------------------------------------------------------------

Test-Step "12 - Similarity / plagiarism engine" {

    $body = @{
        text = "Machine learning is widely used for natural language processing research."
        thesis_id = 12
    } | ConvertTo-Json -Depth 8

    $r = Invoke-RestMethod `
        -Uri "$BASE/api/ai/similarity" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 180

    Show-Json $r

    if (-not $r) {
        throw "Similarity endpoint returned no response."
    }
}

# ------------------------------------------------------------------
# 13. PROPOSAL ANALYSIS
# ------------------------------------------------------------------

Test-Step "13 - Proposal analysis" {

    $body = @{
        proposal = "This research proposes a lightweight transformer model for low-resource Yoruba natural language processing."
        topic = "Low-resource Yoruba NLP"
    } | ConvertTo-Json -Depth 8

    $r = Invoke-RestMethod `
        -Uri "$BASE/api/ai/proposal/analyze" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 240

    Show-Json $r

    if (-not $r) {
        throw "Proposal analysis returned no response."
    }
}

# ------------------------------------------------------------------
# 14. IDEA EXTENSION
# ------------------------------------------------------------------

Test-Step "14 - Research idea extension" {

    $body = @{
        idea = "A retrieval augmented system for low-resource Yoruba research."
    } | ConvertTo-Json -Depth 8

    $r = Invoke-RestMethod `
        -Uri "$BASE/api/ai/ideas/extend" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 240

    Show-Json $r

    if (-not $r) {
        throw "Idea extension returned no response."
    }
}

# ------------------------------------------------------------------
# 15. METADATA
# ------------------------------------------------------------------

Test-Step "15 - Metadata extraction" {

    $body = @{
        text = @"
Title: Low Resource Natural Language Processing for Yoruba
Authors: Afolabi Wilson
Abstract: This study investigates machine learning methods for Yoruba language processing.
Keywords: Yoruba, NLP, transformers, low-resource languages
"@
    } | ConvertTo-Json -Depth 8

    $r = Invoke-RestMethod `
        -Uri "$BASE/api/ai/metadata/extract" `
        -Method POST `
        -ContentType "application/json" `
        -Body $body `
        -TimeoutSec 180

    Show-Json $r

    if (-not $r) {
        throw "Metadata extraction returned no response."
    }
}

# ------------------------------------------------------------------
# SUMMARY
# ------------------------------------------------------------------

Write-Host ""
Write-Host ""
Write-Host "==============================================================" -ForegroundColor Magenta
Write-Host " TEST SUMMARY" -ForegroundColor Magenta
Write-Host "==============================================================" -ForegroundColor Magenta

$Results | Format-Table -AutoSize

$passed = @($Results | Where-Object Status -eq "PASS").Count
$failed = @($Results | Where-Object Status -eq "FAIL").Count

Write-Host ""
Write-Host "PASSED : $passed" -ForegroundColor Green
Write-Host "FAILED : $failed" -ForegroundColor Red
Write-Host ""

if ($failed -eq 0) {
    Write-Host "ALL WORKFLOW TESTS PASSED." -ForegroundColor Green
}
else {
    Write-Host "WORKFLOW PROBLEMS DETECTED." -ForegroundColor Red
    Write-Host "Use the individual FAIL sections above to locate them." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Test complete." -ForegroundColor Cyan
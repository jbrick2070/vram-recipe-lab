$jsons = @(
    "recipes/ab_test/config_A_1_dolly.json",
    "recipes/ab_test/config_B_1_dolly.json",
    "recipes/ab_test/config_A_2_track.json",
    "recipes/ab_test/config_B_2_track.json",
    "recipes/ab_test/config_A_3_foley.json",
    "recipes/ab_test/config_B_3_foley.json"
)

foreach ($j in $jsons) {
    Write-Host "Running $j..."
    ..\.venv\Scripts\python.exe run_recipe.py $j --clamp 15.5
}
Write-Host "ALL A/B TESTS COMPLETE"

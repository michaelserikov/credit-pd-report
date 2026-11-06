Attribute VB_Name = "PortfolioTools"
' Calibration test for the PD calculator workbook.
' Import: open pd_calculator.xlsx, Alt+F11, File > Import File > PortfolioTools.bas, save as .xlsm.
' Then run AddBinomialCheck (Alt+F8), or use =BinomialPValue(defaults, clients, pd) in a cell.
Option Explicit

' Two-sided exact binomial test, the same rule as scipy.stats.binomtest: the p-value is the total probability of all
' outcomes that are no more likely than the observed number of defaults.
Public Function BinomialPValue(ByVal defaults As Long, ByVal clients As Long, ByVal pd As Double) As Variant
    Dim observed As Double, total As Double, prob As Double, i As Long
    If clients <= 0 Or pd <= 0 Or pd >= 1 Or defaults < 0 Or defaults > clients Then
        BinomialPValue = CVErr(xlErrValue)
        Exit Function
    End If
    observed = WorksheetFunction.Binom_Dist(defaults, clients, pd, False)
    For i = 0 To clients
        prob = WorksheetFunction.Binom_Dist(i, clients, pd, False)
        If prob <= observed * (1 + 0.0000001) Then total = total + prob
    Next i
    If total > 1 Then total = 1
    BinomialPValue = total
End Function

' Writes the VBA p-value next to the Python one on the MasterScale sheet, with the difference.
Public Sub AddBinomialCheck()
    Dim ws As Worksheet, r As Long
    Set ws = ThisWorkbook.Worksheets("MasterScale")
    ws.Range("I1").Value = "binomial_p_vba"
    ws.Range("J1").Value = "difference"
    r = 2
    Do While ws.Cells(r, 1).Value <> ""
        ws.Cells(r, 9).Value = BinomialPValue(ws.Cells(r, 6).Value, ws.Cells(r, 5).Value, ws.Cells(r, 4).Value)
        ws.Cells(r, 10).Value = ws.Cells(r, 9).Value - ws.Cells(r, 8).Value
        r = r + 1
    Loop
    MsgBox "Binomial check written for " & (r - 2) & " grades.", vbInformation
End Sub

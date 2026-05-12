-- BULK IMPORT MSSQL (local SQL Server)
-- CSV located on the same PC as SQL Server.
-- If your SQL Server version is < 2017, keep FORMAT='CSV' commented.

DECLARE @base_path NVARCHAR(4000) = N'C:\Users\mamsylla\OneDrive - BANK OF AFRICA(1)\Documents\Projets\2025\Plateforme notatio kyc v2\data\';

DECLARE @filiales TABLE(code NVARCHAR(10));
INSERT INTO @filiales(code) VALUES (N'SN'),(N'CI'),(N'BF'),(N'TG'),(N'NE');

-- Staging tables (temp)
IF OBJECT_ID('tempdb..#anomalie_stage') IS NULL
BEGIN
    CREATE TABLE #anomalie_stage (
        AGENCE NVARCHAR(200) NULL,
        LIB_AGENCE NVARCHAR(200) NULL,
        EXPL NVARCHAR(200) NULL,
        CLIENT NVARCHAR(200) NULL,
        ANOMALIE_AGE NVARCHAR(200) NULL,
        ANOMALIE_DATE_EER NVARCHAR(200) NULL,
        ANOMALIE_CIN NVARCHAR(200) NULL,
        PPE NVARCHAR(200) NULL
    );
END

IF OBJECT_ID('tempdb..#daterev_stage') IS NULL
BEGIN
    CREATE TABLE #daterev_stage (
        AGENCE NVARCHAR(200) NULL,
        LIB_AGENCE NVARCHAR(200) NULL,
        EXPL NVARCHAR(200) NULL,
        CLIENT NVARCHAR(200) NULL,
        DATEREV NVARCHAR(50) NULL,
        PPE NVARCHAR(200) NULL,
        RISQUE NVARCHAR(200) NULL
    );
END

IF OBJECT_ID('tempdb..#taux_filiale_stage') IS NULL
BEGIN
    CREATE TABLE #taux_filiale_stage (
        FLUX_PM NVARCHAR(50) NULL,
        FLUX_PP NVARCHAR(50) NULL,
        STOCK_PM NVARCHAR(50) NULL,
        STOCK_PP NVARCHAR(50) NULL,
        [DATE] NVARCHAR(50) NULL
    );
END

DECLARE @code NVARCHAR(10);
DECLARE @file NVARCHAR(4000);
DECLARE @sql NVARCHAR(MAX);

DECLARE cur CURSOR LOCAL FAST_FORWARD FOR
    SELECT code FROM @filiales;

OPEN cur;
FETCH NEXT FROM cur INTO @code;
WHILE @@FETCH_STATUS = 0
BEGIN
    -- =============================
    -- ANOMALIES
    -- =============================
    DELETE FROM dbo.kyc_anomalie WHERE FILIALE = N'BOA ' + @code;
    TRUNCATE TABLE #anomalie_stage;

    SET @file = @base_path + N'anomalies_' + @code + N'.csv';
    SET @sql = N'
        BULK INSERT #anomalie_stage
        FROM ''' + @file + N'''
        WITH (
            FIRSTROW = 2,
            FIELDTERMINATOR = '';'',
            ROWTERMINATOR = ''0x0a'',
            CODEPAGE = ''65001''
            -- ,FORMAT=''CSV'', FIELDQUOTE=''"''  -- Uncomment for SQL Server 2017+
        );';
    EXEC(@sql);

    INSERT INTO dbo.kyc_anomalie
        (FILIALE, AGENCE, LIB_AGENCE, EXPL, CLIENT, ANOMALIE_AGE, ANOMALIE_DATE_EER, ANOMALIE_CIN, PPE)
    SELECT
        N'BOA ' + @code,
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(AGENCE, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(LIB_AGENCE, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(EXPL, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(CLIENT, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(ANOMALIE_AGE, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(ANOMALIE_DATE_EER, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(ANOMALIE_CIN, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(PPE, '"', ''))), ''), '')
    FROM #anomalie_stage;

    -- =============================
    -- DATEREV (scoring_{code}.csv)
    -- =============================
    DELETE FROM dbo.kyc_daterev WHERE FILIALE = N'BOA ' + @code;
    TRUNCATE TABLE #daterev_stage;

    SET @file = @base_path + N'scoring_' + @code + N'.csv';
    SET @sql = N'
        BULK INSERT #daterev_stage
        FROM ''' + @file + N'''
        WITH (
            FIRSTROW = 2,
            FIELDTERMINATOR = '';'',
            ROWTERMINATOR = ''0x0a'',
            CODEPAGE = ''65001''
            -- ,FORMAT=''CSV'', FIELDQUOTE=''"''  -- Uncomment for SQL Server 2017+
        );';
    EXEC(@sql);

    INSERT INTO dbo.kyc_daterev
        (FILIALE, AGENCE, LIB_AGENCE, EXPL, CLIENT, DATEREV, PPE, RISQUE)
    SELECT
        N'BOA ' + @code,
        LEFT(NULLIF(LTRIM(RTRIM(REPLACE(AGENCE, '"', ''))), ''), 10),
        LEFT(NULLIF(LTRIM(RTRIM(REPLACE(LIB_AGENCE, '"', ''))), ''), 50),
        LEFT(NULLIF(LTRIM(RTRIM(REPLACE(EXPL, '"', ''))), ''), 10),
        LEFT(NULLIF(LTRIM(RTRIM(REPLACE(CLIENT, '"', ''))), ''), 10),
        COALESCE(
            TRY_CONVERT(date, REPLACE(DATEREV, '"', ''), 103),
            TRY_CONVERT(date, REPLACE(DATEREV, '"', ''), 120)
        ),
        LEFT(NULLIF(LTRIM(RTRIM(REPLACE(PPE, '"', ''))), ''), 20),
        LEFT(NULLIF(LTRIM(RTRIM(REPLACE(RISQUE, '"', ''))), ''), 20)
    FROM #daterev_stage;

    -- =============================
    -- TAUX EVOLUTION FILIALE
    -- =============================
    DELETE FROM dbo.kyc_tauxevolution_filiale WHERE filiale = N'BOA ' + @code;
    TRUNCATE TABLE #taux_filiale_stage;

    SET @file = @base_path + N'suivi_fiabilisation_' + @code + N'.csv';
    SET @sql = N'
        BULK INSERT #taux_filiale_stage
        FROM ''' + @file + N'''
        WITH (
            FIRSTROW = 2,
            FIELDTERMINATOR = '';'',
            ROWTERMINATOR = ''0x0a'',
            CODEPAGE = ''65001''
            -- ,FORMAT=''CSV'', FIELDQUOTE=''"''  -- Uncomment for SQL Server 2017+
        );';
    EXEC(@sql);

    INSERT INTO dbo.kyc_tauxevolution_filiale
        (filiale, flux_PM, flux_PP, stock_PM, stock_PP, [date], created_at)
    SELECT
        N'BOA ' + @code,
        TRY_CONVERT(float, REPLACE(REPLACE(REPLACE(FLUX_PM, '"', ''), '%', ''), ',', '.')),
        TRY_CONVERT(float, REPLACE(REPLACE(REPLACE(FLUX_PP, '"', ''), '%', ''), ',', '.')),
        TRY_CONVERT(float, REPLACE(REPLACE(REPLACE(STOCK_PM, '"', ''), '%', ''), ',', '.')),
        TRY_CONVERT(float, REPLACE(REPLACE(REPLACE(STOCK_PP, '"', ''), '%', ''), ',', '.')),
        d.date_val,
        SYSUTCDATETIME()
    FROM #taux_filiale_stage
    CROSS APPLY (
        SELECT COALESCE(
            TRY_CONVERT(date, REPLACE([DATE], '"', ''), 103),
            TRY_CONVERT(date, REPLACE([DATE], '"', ''), 120)
        ) AS date_val
    ) d
    WHERE d.date_val IS NOT NULL;

    FETCH NEXT FROM cur INTO @code;
END

CLOSE cur;
DEALLOCATE cur;

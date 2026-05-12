-- BULK IMPORT MSSQL for import_kyc.py (Kyc_pm / Kyc_pp)
-- CSV located on the same PC as SQL Server.
-- If your SQL Server version is < 2017, keep FORMAT='CSV' commented.
-- IMPORTANT: BULK INSERT matches columns by ORDER, not by header name.
-- Ensure the column order below matches your CSV files.

DECLARE @base_path NVARCHAR(4000) = N'C:\Users\mamsylla\OneDrive - BANK OF AFRICA(1)\Documents\Projets\2025\Plateforme notatio kyc v2\data\';

DECLARE @filiales TABLE(code NVARCHAR(10));
INSERT INTO @filiales(code) VALUES (N'TG'); -- Ajouter d'autres codes si besoin

-- Staging tables (temp)
IF OBJECT_ID('tempdb..#pm_stage') IS NULL
BEGIN
    CREATE TABLE #pm_stage (
        AGENCE NVARCHAR(200) NULL,
        LIB_AGENCE NVARCHAR(200) NULL,
        EXPL NVARCHAR(200) NULL,
        CLIENT NVARCHAR(200) NULL,
        AGEC NVARCHAR(200) NULL,
        CODAPE NVARCHAR(200) NULL,
        IDM NVARCHAR(200) NULL,
        RCSNO NVARCHAR(200) NULL,
        CAPITAL NVARCHAR(200) NULL,
        CA NVARCHAR(200) NULL,
        RESULTAT NVARCHAR(200) NULL,
        ORIGINE_REV NVARCHAR(200) NULL,
        DATOUV NVARCHAR(200) NULL,
        TEL NVARCHAR(200) NULL,
        DEVISE NVARCHAR(200) NULL,
        RESID NVARCHAR(200) NULL
    );
END

IF OBJECT_ID('tempdb..#pp_stage') IS NULL
BEGIN
    CREATE TABLE #pp_stage (
        AGENCE NVARCHAR(200) NULL,
        LIB_AGENCE NVARCHAR(200) NULL,
        EXPL NVARCHAR(200) NULL,
        CLIENT NVARCHAR(200) NULL,
        CODAPE NVARCHAR(200) NULL,
        IDP NVARCHAR(200) NULL,
        PAYNAIS NVARCHAR(200) NULL,
        PROFESSION NVARCHAR(200) NULL,
        ADRESSE NVARCHAR(200) NULL,
        PAYS_RESID NVARCHAR(200) NULL,
        NUMID NVARCHAR(200) NULL,
        SALAIRE NVARCHAR(200) NULL,
        ORIGINE_REV NVARCHAR(200) NULL,
        DATVALID NVARCHAR(200) NULL,
        TEL NVARCHAR(200) NULL,
        DATOUV NVARCHAR(200) NULL,
        PPE NVARCHAR(200) NULL,
        DEVISE NVARCHAR(200) NULL,
        RESID NVARCHAR(200) NULL
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
    -- KYC PM
    -- =============================
    DELETE FROM dbo.kyc_pm WHERE FILIALE = N'BOA ' + @code;
    TRUNCATE TABLE #pm_stage;

    SET @file = @base_path + N'pm_' + @code + N'_STOCK_F.csv';
    SET @sql = N'
        BULK INSERT #pm_stage
        FROM ''' + @file + N'''
        WITH (
            FIRSTROW = 2,
            FIELDTERMINATOR = '';'',
            ROWTERMINATOR = ''0x0a'',
            CODEPAGE = ''65001''
            -- ,FORMAT=''CSV'', FIELDQUOTE=''"''  -- Uncomment for SQL Server 2017+
        );';
    EXEC(@sql);

    INSERT INTO dbo.kyc_pm
        (FILIALE, AGENCE, LIB_AGENCE, EXPL, CLIENT, AGEC, CODAPE, IDM, RCSNO, CAPITAL, CA, RESULTAT,
         ORIGINE_REV, DATOUV, TEL, DEVISE, RESID)
    SELECT
        N'BOA ' + @code,
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(AGENCE, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(LIB_AGENCE, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(EXPL, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(CLIENT, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(AGEC, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(CODAPE, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(IDM, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(RCSNO, '"', ''))), ''), ''),
        REPLACE(REPLACE(ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(CAPITAL, '"', ''))), ''), ''), ' ', ''), ',', '.'),
        REPLACE(REPLACE(ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(CA, '"', ''))), ''), ''), ' ', ''), ',', '.'),
        REPLACE(REPLACE(ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(RESULTAT, '"', ''))), ''), ''), ' ', ''), ',', '.'),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(ORIGINE_REV, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(DATOUV, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(TEL, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(DEVISE, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(RESID, '"', ''))), ''), '')
    FROM #pm_stage;

    -- =============================
    -- KYC PP
    -- =============================
    DELETE FROM dbo.kyc_pp WHERE FILIALE = N'BOA ' + @code;
    TRUNCATE TABLE #pp_stage;

    SET @file = @base_path + N'pp_' + @code + N'_STOCK_F.csv';
    SET @sql = N'
        BULK INSERT #pp_stage
        FROM ''' + @file + N'''
        WITH (
            FIRSTROW = 2,
            FIELDTERMINATOR = '';'',
            ROWTERMINATOR = ''0x0a'',
            CODEPAGE = ''65001''
            -- ,FORMAT=''CSV'', FIELDQUOTE=''"''  -- Uncomment for SQL Server 2017+
        );';
    EXEC(@sql);

    INSERT INTO dbo.kyc_pp
        (FILIALE, AGENCE, LIB_AGENCE, EXPL, CLIENT, CODAPE, IDP, PAYNAIS, PROFESSION, ADRESSE, PAYS_RESID,
         NUMID, SALAIRE, ORIGINE_REV, DATVALID, TEL, DATOUV, PPE, DEVISE, RESID)
    SELECT
        N'BOA ' + @code,
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(AGENCE, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(LIB_AGENCE, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(EXPL, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(CLIENT, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(CODAPE, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(IDP, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(PAYNAIS, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(PROFESSION, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(ADRESSE, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(PAYS_RESID, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(NUMID, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(SALAIRE, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(ORIGINE_REV, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(DATVALID, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(TEL, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(DATOUV, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(PPE, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(DEVISE, '"', ''))), ''), ''),
        ISNULL(NULLIF(LTRIM(RTRIM(REPLACE(RESID, '"', ''))), ''), '')
    FROM #pp_stage;

    FETCH NEXT FROM cur INTO @code;
END

CLOSE cur;
DEALLOCATE cur;

"""
Main Job Crawler Controller
Reads company data and orchestrates scraping across different ATS platforms
"""
import os
import logging
import argparse
from .crawler_logger import CrawlerLogger
from .data_controller import DataController
from .client import JobCrawlerController

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',  # Simplified format without timestamps
    handlers=[
        logging.FileHandler('job_crawler.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

def main():
    
    # Get current directory and data directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_data_dir = os.path.join(script_dir, '..', '..', 'data')
    default_data_dir = os.path.abspath(default_data_dir)
    
    
    parser = argparse.ArgumentParser(description='Job Crawler - Scrape jobs from multiple ATS platforms')
    parser.add_argument('input', nargs='?', default=os.path.join(default_data_dir, 'job_search.csv'),
                    help='Company input CSV or legacy Google Sheet URL/ID; ignored for postgres input')
    parser.add_argument('-t', '--input-type', choices=['csv', 'yaml', 'sheets', 'postgres'], default='csv',
                    help='Input source type (default: csv)')
    parser.add_argument('--input-worksheet',
                    help='Worksheet name to read when using Google Sheets input')
    parser.add_argument('-l', '--limit', type=int, help='Limit number of companies to process')
    parser.add_argument('-d', '--delay', type=float, default=0.2,
                    help='Delay between requests (seconds)')
    parser.add_argument('-o', '--output-dir', default=default_data_dir,
                    help='Output directory for job files')
    parser.add_argument('-w', '--workers', type=int, default=None,
                    help='Number of concurrent scrapers to run (default: auto)')
    parser.add_argument('--output-sheet',
                    help='Google Sheet URL or spreadsheet ID to update with all_jobs.csv after scraping')
    parser.add_argument('--output-worksheet', default='all_jobs',
                    help='Worksheet name to update when --output-sheet is provided')
    
    args = parser.parse_args()
    
    CrawlerLogger.info_message("\n🤖 Job Crawler v2.0\n")
    
    # Initialize controller
    controller = JobCrawlerController(delay=args.delay, output_dir=args.output_dir, max_workers=args.workers)
    data_ctrl = DataController()
    # Load data
    try:
        CrawlerLogger.info_message(f"📥 Loading from: {args.input}")
        if args.input_type == 'postgres':
            from .postgres_storage import PostgresJobStorage
            df = PostgresJobStorage().load_companies()
        elif args.input_type == 'yaml':
            df = data_ctrl.load_data_from_yaml(args.input)
        elif args.input_type == 'sheets':
            df = data_ctrl.load_data_from_google_sheet(args.input, args.input_worksheet)
        else:
            df = data_ctrl.load_data_from_csv(args.input)
        
        CrawlerLogger.info_message(f"✓ Loaded {len(df)} companies\n")
        
    except Exception as e:
        CrawlerLogger.error_message(f"❌ Failed to load data: {e}")
        return
    
    # Process companies
    try:
        controller.process_companies(df, limit=args.limit)
        if args.input_type == 'postgres':
            try:
                PostgresJobStorage().record_source_health(controller.source_health_results)
            except Exception as error:
                logger.warning("Could not record source health (%s)", type(error).__name__)
        if args.output_sheet:
            output_csv = os.path.join(args.output_dir, 'all_jobs.csv')
            output_ctrl = DataController(output_csv)
            output_ctrl.export_jobs_to_google_sheet(args.output_sheet, args.output_worksheet)
            
    except KeyboardInterrupt:
        CrawlerLogger.interrupted_warning()
    except Exception as e:
        CrawlerLogger.general_error(e)



if __name__ == '__main__':
    main()

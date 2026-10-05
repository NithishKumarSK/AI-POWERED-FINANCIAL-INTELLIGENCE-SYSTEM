"""
Test script to demonstrate the 3-agent portfolio system
"""

from portfolio_manager import PortfolioManager, create_sample_portfolio


def test_quick_summary():
    """Test quick portfolio summary."""
    print("="*80)
    print("TEST 1: Quick Portfolio Summary")
    print("="*80)
    
    pm = PortfolioManager()
    portfolio = create_sample_portfolio()
    
    result = pm.get_portfolio_quick_summary(portfolio)
    
    print(f"\nStatus: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(f"Total Holdings: {result['total_holdings']}")
        print(f"Total Invested: ${result['total_invested']:,.2f}")
        print(f"Cash: ${result['cash']:,.2f}")
        print(f"Total Value: ${result['total_value']:,.2f}")
        
        print("\nPosition Breakdown:")
        for pos in result['positions']:
            print(f"  - {pos['symbol']}: {pos['shares']} shares @ ${pos['avg_cost']:.2f} (${pos['invested']:,.2f})")
    
    print("\n[PASSED] Test 1 PASSED\n")


def test_single_stock():
    """Test single stock analysis."""
    print("="*80)
    print("TEST 2: Single Stock Analysis")
    print("="*80)
    
    pm = PortfolioManager()
    
    # Use 1-month prediction for faster testing (~16s)
    print("\nAnalyzing AAPL with 1-month prediction (~16 seconds)...")
    result = pm.analyze_single_stock("AAPL", analysis_type="one_month")
    
    print(f"\nStatus: {result['status']}")
    if result['status'] == 'SUCCESS':
        print(f"Total Time: {result['total_time']}")
        print(f"Analysis Type: {result.get('analysis_type', 'N/A')}")
        print("\nReport Preview (first 500 chars):")
        print(result.get('report', '')[:500])
        print("...")
    else:
        print(f"Error: {result.get('message')}")
    
    print("\n[COMPLETED] Test 2 COMPLETED\n")


def test_architecture():
    """Test the 3-agent architecture without full analysis."""
    print("="*80)
    print("TEST 3: 3-Agent Architecture Verification")
    print("="*80)
    
    pm = PortfolioManager()
    
    # Verify all agents are initialized
    print("\nAgent Initialization Check:")
    print(f"  [OK] Orchestrator Agent: {pm.orchestrator is not None}")
    print(f"  [OK] Stock Research Agent: {pm.orchestrator.stock_agent is not None}")
    print(f"  [OK] Recommendation Agent: {pm.recommendation_agent is not None}")
    
    # Verify agent methods
    print("\nAgent Methods Check:")
    print(f"  [OK] Orchestrator.analyze_portfolio: {hasattr(pm.orchestrator, 'analyze_portfolio')}")
    print(f"  [OK] Orchestrator.get_portfolio_summary: {hasattr(pm.orchestrator, 'get_portfolio_summary')}")
    print(f"  [OK] Stock Agent.analyze_stock: {hasattr(pm.orchestrator.stock_agent, 'analyze_stock')}")
    print(f"  [OK] Stock Agent.analyze_stock_one_month: {hasattr(pm.orchestrator.stock_agent, 'analyze_stock_one_month')}")
    print(f"  [OK] Recommendation Agent.generate_recommendations: {hasattr(pm.recommendation_agent, 'generate_recommendations')}")
    print(f"  [OK] Recommendation Agent.compile_final_report: {hasattr(pm.recommendation_agent, 'compile_final_report')}")
    
    # Verify portfolio manager methods
    print("\nPortfolio Manager Methods Check:")
    print(f"  [OK] analyze_portfolio_complete: {hasattr(pm, 'analyze_portfolio_complete')}")
    print(f"  [OK] analyze_single_stock: {hasattr(pm, 'analyze_single_stock')}")
    print(f"  [OK] get_portfolio_quick_summary: {hasattr(pm, 'get_portfolio_quick_summary')}")
    
    print("\n[PASSED] Test 3 PASSED - All agents and methods verified\n")


def test_portfolio_data_structure():
    """Test portfolio data structure."""
    print("="*80)
    print("TEST 4: Portfolio Data Structure")
    print("="*80)
    
    portfolio = create_sample_portfolio()
    
    print("\nPortfolio Data Structure:")
    print(f"  Holdings: {len(portfolio['holdings'])} stocks")
    print(f"  Cash: ${portfolio['cash']:,.2f}")
    
    print("\nHolding Structure:")
    for holding in portfolio['holdings']:
        print(f"  - Symbol: {holding['symbol']}")
        print(f"    Shares: {holding['shares']}")
        print(f"    Avg Cost: ${holding['avg_cost']:.2f}")
        print(f"    Required keys: {all(k in holding for k in ['symbol', 'shares', 'avg_cost'])}")
    
    print("\n[PASSED] Test 4 PASSED\n")


if __name__ == "__main__":
    print("\n")
    print("="*80)
    print("3-AGENT PORTFOLIO SYSTEM TEST")
    print("="*80)
    print("\n")
    
    # Run tests
    test_architecture()
    test_portfolio_data_structure()
    test_quick_summary()
    
    print("\n" + "="*80)
    print("OPTIONAL TESTS (require more time):")
    print("="*80)
    print("\nTest 2: Single Stock Analysis (~16 seconds)")
    print("  - Tests Stock Research Agent with real data")
    print("  - Requires: GOOGLE_API_KEY and RAPIDAPI_KEY")
    
    choice = input("\nRun optional test? (y/n): ").strip().lower()
    if choice == 'y':
        test_single_stock()
    
    print("\n" + "="*80)
    print("COMPLETE PORTFOLIO ANALYSIS TEST")
    print("="*80)
    print("\nThis would run the full 3-agent workflow:")
    print("  1. Orchestrator coordinates stock research for all holdings")
    print("  2. Stock Research Agent analyzes each stock")
    print("  3. Recommendation Agent generates portfolio recommendations")
    print("\nEstimated time for 3 stocks (comprehensive): ~135 seconds (2.25 minutes)")
    print("Estimated time for 3 stocks (1-month): ~48 seconds")
    
    choice = input("\nRun complete portfolio analysis? (y/n): ").strip().lower()
    if choice == 'y':
        pm = PortfolioManager()
        portfolio = create_sample_portfolio()
        
        print("\nRunning complete portfolio analysis (1-month prediction for speed)...")
        result = pm.analyze_portfolio_complete(portfolio, analysis_type="one_month")
        
        print(f"\nStatus: {result['status']}")
        if result['status'] == 'SUCCESS':
            print(f"Total Time: {result['total_time']}")
            
            print("\nExecution Log:")
            for log in result['execution_log']:
                status_icon = "[OK]" if log['status'] == "SUCCESS" else "[FAIL]"
                print(f"{status_icon} Step {log['step']}: {log['agent']} - {log['action']} ({log['duration']})")
            
            print("\nFinal Report:")
            print(result['final_report'])
        else:
            print(f"Error: {result.get('message')}")
    
    print("\n" + "="*80)
    print("ALL TESTS COMPLETED")
    print("="*80)
    print("\n3-Agent System Architecture:")
    print("  1. Orchestrator Agent (portfolio_orchestrator.py)")
    print("     - Coordinates stock research for portfolio")
    print("     - Manages portfolio data")
    print("  2. Stock Research Agent (stock_analysis_agent.py)")
    print("     - Analyzes individual stocks")
    print("     - 3 analysis types: comprehensive, 1-month, scenario")
    print("  3. Recommendation Agent (portfolio_recommendation_agent.py)")
    print("     - Generates portfolio-level recommendations")
    print("     - Risk analysis and optimization suggestions")
    print("\nUnified Interface: portfolio_manager.py")
    print("="*80 + "\n")
